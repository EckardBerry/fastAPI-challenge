import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from slowapi import Limiter
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.db.invoice_manager_db import (
    count_invoices,
    find_recent_matching_invoice,
    get_joined_invoice_customer_by_id,
    list_invoices_with_customers,
    update_invoice_status,
)
from src.exception_handlers import (
    AppError,
    BadRequestError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    FakePayFailedError,
    InvoiceNotFoundError,
    InvoiceNotPendingError,
)
from src.models.card import MaskedCard, PayCardBody, parse_pay_card
from src.models.enums import Status
from src.models.invoice import InvoiceRequest, InvoiceResponse
from src.models.model_mappers import map_db_to_invoice_response
from src.services.invoice_service import InvoicingService

logger = logging.getLogger(__name__)


def build_invoice_router(
    invoice_service: InvoicingService,
    limiter: Limiter,
) -> APIRouter:
    """Invoice-related routes; paths stay the same as when they lived on app.py file."""
    router = APIRouter(tags=["Invoices"])

    @router.get("/invoice/{invoice_id}")
    async def get_invoice(response: Response, invoice_id: UUID = Path(...)):
        """Get an invoice by its ID."""
        response.status_code, json_response = await invoice_service.get_invoice(
            invoice_id
        )
        return json_response

    @router.get(
        "/invoices",
        response_model=list[InvoiceResponse],
        response_model_exclude_none=True,
    )
    async def list_invoices(
        response: Response,
        invoice_status: Annotated[
            Optional[Status],
            Query(
                alias="invoiceStatus",
                description="Filter by PAID, PENDING, or CANCELLED (omit for all)",
            ),
        ] = None,
        page: Annotated[int, Query(ge=1, description="1-based page index")] = 1,
        page_size: Annotated[
            int,
            Query(
                ge=1,
                le=100,
                alias="pageSize",
                description="Rows per page (default 10)",
            ),
        ] = 10,
    ):
        """
        Return a page of invoices (with customer data) as JSON.

        Query parameters (what callers put in the URL after ``?``):

        - **invoiceStatus** (optional): If you omit it, you get every status. If you set it to
          ``PAID``, ``PENDING``, or ``CANCELLED``, only rows with that status are counted and
          returned. In Python the parameter is named ``invoice_status``; FastAPI accepts
          ``invoiceStatus`` in the URL because of the ``alias``.
        - **page** (optional, default ``1``): Which page you want, counting from 1 (not 0).
          Must be at least 1.
        - **pageSize** (optional, default ``10``): How many invoices per page. In code this is
          ``page_size``; the URL name is ``pageSize`` (alias). Allowed range is 1 through 100.

        **Why it looks like ``Annotated[..., Query(...)]`` in code:** FastAPI uses those
        annotations to know each argument comes from the query string, to validate numbers
        (e.g. page and page size bounds), to document the API, and to map camelCase query names
        to snake_case Python names.

        **Pagination in practice:** The service skips ``(page - 1) * pageSize`` rows and then
        takes at most ``pageSize`` rows. Response headers tell you the full picture:
        ``X-Total-Count`` (how many rows match the filter), ``X-Page`` (current page),
        ``X-Page-Size`` (rows per page for this request).

        Examples:

            All: GET /invoices

            Filter: GET /invoices?invoiceStatus=PENDING

            Page 2, 10 per page: GET /invoices?page=2&pageSize=10

            Combined: GET /invoices?invoiceStatus=PENDING&page=1&pageSize=10
        """
        status_filter = invoice_status.value if invoice_status is not None else None
        offset = (page - 1) * page_size

        logger.debug(
            "Listing invoices: status_filter=%s page=%s page_size=%s offset=%s",
            status_filter,
            page,
            page_size,
            offset,
        )

        try:
            total = count_invoices(invoice_status=status_filter)
            records = list_invoices_with_customers(
                invoice_status=status_filter,
                limit=page_size,
                offset=offset,
            )
        except OperationalError:
            logger.exception("Database unavailable while listing invoices")
            raise DatabaseUnavailableError()
        except SQLAlchemyError:
            logger.exception("Database error while listing invoices")
            raise DatabaseOperationError("Failed to load invoices")

        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)

        logger.info(
            "Returned %s invoice(s) (total matching=%s, page=%s)",
            len(records),
            total,
            page,
        )

        return [
            map_db_to_invoice_response(invoice_db, customer_db)
            for invoice_db, customer_db in records
        ]

    @router.post("/invoice", response_model=InvoiceResponse, status_code=201)
    @limiter.limit("30/minute")
    async def create_invoice(request: Request, invoice_data: InvoiceRequest):
        """
        Create an invoice.

        Mitigations for rapid repeats:
        - Rate limit (30/minute per client IP).
        - If the body has no card, a recent record with the same customer, description, and amount
          is treated as the same submit and returned.

        Two identical requests before the first commit can still cause a race condition;
        use spacing or the rate limit to try and prevent this.
        """
        if invoice_data.card is None:
            recent = find_recent_matching_invoice(
                customer_id=invoice_data.customer_id,
                job_description=invoice_data.job_description,
                amount=float(invoice_data.amount),
            )
            if recent is not None:
                invoice_db, customer_db = recent
                logger.info(
                    "Duplicate POST suppressed: returning existing invoice %s",
                    invoice_db.id,
                )
                return map_db_to_invoice_response(invoice_db, customer_db)

        try:
            return await invoice_service.execute_invoice_creation(invoice_data)
        except AppError:
            raise
        except Exception as error:
            logger.exception("Unexpected error creating invoice")
            raise BadRequestError(str(error))

    @router.post(
        "/invoice/pay/{invoice_id}",
        response_model=InvoiceResponse,
        status_code=201,
    )
    async def pay_pending_invoice(
        invoice_id: Annotated[UUID, Path(description="Invoice UUID")],
        card_body: PayCardBody,
    ):
        # Checking the card body is valid and raising an exception if it is not.
        card = parse_pay_card(card_body)
        
        db_row = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if db_row is None:
            raise InvoiceNotFoundError(str(invoice_id))
        invoice_db, customer_db = db_row
        if invoice_db.invoice_status != Status.PENDING.value:
            raise InvoiceNotPendingError(invoice_db.invoice_status)

        payment_successful = await invoice_service.authorize_payment(
            amount=invoice_db.amount,
            transaction_id=str(invoice_id),
            card=card,
        )
        if not payment_successful:
            raise FakePayFailedError()

        updated = update_invoice_status(str(invoice_id), Status.PAID)
        if not updated:
            raise InvoiceNotFoundError(str(invoice_id))

        invoice_db, customer_db = get_joined_invoice_customer_by_id(
            invoice_id=str(invoice_id)
        )
        invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
        masked_card = MaskedCard.from_card(card)
        return invoice_response.model_copy(update={"card": masked_card})

    return router
