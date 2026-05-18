import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from slowapi import Limiter
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.db.invoice_manager_db import (
    count_invoices,
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
from src.models.invoice_model import InvoiceRequest, InvoiceResponse
from src.models.model_mappers import map_db_to_invoice_response
from src.services.invoice_service import InvoicingService

logger = logging.getLogger(__name__)


class InvoiceRoutes:
    """Invoice-related routes; paths stay the same as when they lived on app.py file."""

    def __init__(
        self,
        invoice_service: InvoicingService,
        limiter: Limiter,
    ) -> None:
        self.router = APIRouter(tags=["Invoices"])
        self._invoice_service = invoice_service
        self._limiter = limiter
        self._register_routes()

    def _register_routes(self) -> None:
        invoice_service = self._invoice_service
        limiter = self._limiter
        router = self.router

        @router.get(
            "/invoice/{invoice_id}",
            response_model=InvoiceResponse,
            response_model_exclude_none=True,
        )
        async def get_invoice(invoice_id: UUID = Path(...)):
            """Get an invoice by its ID."""
            return await invoice_service.get_invoice(invoice_id)

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

            - invoiceStatus (optional): If you omit it, you get every status. If you set it to
              PAID, PENDING, or CANCELLED, only rows with that status are counted and
              returned.
            - page (optional, default 1): Which page you want, counting from 1 (not 0).
              Must be at least 1.
            - pageSize (optional, default 10): How many invoices per page.

            Annotated[..., Query(...)] in code: FastAPI uses those
            annotations to know each argument comes from the query string, to validate numbers
            (e.g. page and page size bounds), to document the API, and to map camelCase query names
            to snake_case Python names.

            Pagination: The service skips (page - 1) * pageSize rows and then
            takes at most pageSize rows. Response headers tell you the full picture:
            X-Total-Count (how many rows match the filter), X-Page (current page),
            X-Page-Size (rows per page for this request).

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
                # Total number of invoices matching the filter.
                total = count_invoices(invoice_status=status_filter)
                records = list_invoices_with_customers(
                    invoice_status=status_filter,
                    limit=page_size,
                    offset=offset,
                )
            except OperationalError:
                logger.exception("Database unavailable while listing invoices")
                raise DatabaseUnavailableError()
            except SQLAlchemyError as sql_error:
                logger.exception(f"Database error while listing invoices: {sql_error}")
                raise DatabaseOperationError("Failed to load invoices")

            # Update the response headers with the computed values.
            response.headers["X-Total-Count"] = str(total)
            response.headers["X-Page"] = str(page)
            response.headers["X-Page-Size"] = str(page_size)

            # Return a list of InvoiceResponse serialized invoices.
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
            - A recent record with the same customer, description, and amount is treated as the
              same submit and returned.

            Two identical requests before the first commit can still cause a race condition;
            use spacing or the rate limit to try and prevent this.
            """
            # invoice_data is an instance of InvoiceRequest which is a Pydantic instance of all the fields
            # serialized and validated by the InvoiceRequest serializer
            existing_invoice = invoice_data._duplicate_invoice_response
            if existing_invoice is not None:
                return existing_invoice

            try:
                # Create new invoice and charge via FakePay service if card is provided.
                return await invoice_service.execute_invoice_creation(invoice_data)
            except AppError:
                raise
            except Exception as error:
                logger.exception(f"Unexpected error creating invoice: {error}")
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

            # Query db for invoice and customer.
            db_row = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
            if db_row is None:
                raise InvoiceNotFoundError(str(invoice_id))
            invoice_db, customer_db = db_row

            if invoice_db.invoice_status != Status.PENDING.value:
                raise InvoiceNotPendingError(invoice_db.invoice_status)

            # Authorize payment via FakePay service.
            payment_successful = await invoice_service.authorize_payment(
                amount=invoice_db.amount,
                transaction_id=str(invoice_id),
                card=card,
            )
            if not payment_successful:
                raise FakePayFailedError()

            # Update invoice status to PAID.
            updated = update_invoice_status(str(invoice_id), Status.PAID)
            if not updated:
                raise InvoiceNotFoundError(str(invoice_id))

            # Get the updated invoice and customer fresh from the db.
            invoice_db, customer_db = get_joined_invoice_customer_by_id(
                invoice_id=str(invoice_id)
            )
            # Return a serialized InvoiceResponse for the updated invoice.
            invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
            # Mask the card number, do not return the card number in the response.
            masked_card = MaskedCard.from_card(card)
            # Return the updated invoice with the masked card.
            return invoice_response.model_copy(update={"card": masked_card})


def build_invoice_router(
    invoice_service: InvoicingService,
    limiter: Limiter,
) -> APIRouter:
    """Return the invoice router to be used in the main.py file."""
    return InvoiceRoutes(invoice_service, limiter).router
