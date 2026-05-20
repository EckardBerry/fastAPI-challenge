import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from slowapi import Limiter
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.db.invoice_manager_db import (
    count_invoices,
    list_invoices_with_customers,
)
from src.exception_handlers import (
    DatabaseOperationError,
    DatabaseUnavailableError,
)
from src.models.card import PayCardBody
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
            # Calling the appropriate function from the serializer to create an invoice
            create_invoice_response = await InvoiceRequest.process_creation_request(
                invoice_data=invoice_data,
                invoice_service=invoice_service,
            )
            # Return an InvoiceRequest object
            return create_invoice_response

        @router.post(
            "/invoice/pay/{invoice_id}",
            response_model=InvoiceResponse,
            status_code=201,
        )
        async def pay_pending_invoice(
            invoice_id: Annotated[UUID, Path(description="Invoice UUID")],
            card_body: PayCardBody,
        ):
            # Calling the appropriate function from the serializer to process the payment
            payment_response = await InvoiceResponse.process_payment_request(
                invoice_id=invoice_id,
                card_body=card_body,
                invoice_service=invoice_service
            )
            # Return an InvoiceResponse object
            return payment_response


def build_invoice_router(
    invoice_service: InvoicingService,
    limiter: Limiter,
) -> APIRouter:
    """Return the invoice router to be used in the main.py file."""
    return InvoiceRoutes(invoice_service, limiter).router
