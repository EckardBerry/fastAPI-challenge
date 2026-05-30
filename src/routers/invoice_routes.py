import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Response

from src.schemas.auth import require_authentication
from src.schemas.card import PayCardBody
from src.schemas.invoice_schema import InvoiceRequest, InvoiceResponse
from src.schemas.rate_limit import require_rate_limit
from src.services.invoice_service import InvoicingService

logger = logging.getLogger(__name__)


class InvoiceRoutes:
    """Invoice-related routes; paths stay the same as when they lived on app.py file."""

    def __init__(
        self,
        invoice_service: InvoicingService,
    ) -> None:
        self.router = APIRouter(tags=["Invoices"])
        self._invoice_service = invoice_service
        self._register_routes()

    def _register_routes(self) -> None:
        invoice_service = self._invoice_service
        router = self.router
        @router.get(
            "/invoice/{invoice_id}",
            response_model=InvoiceResponse,
            response_model_exclude_none=True,
            dependencies=[require_authentication],
        )
        async def get_invoice(invoice_id: UUID = Path(...)):
            """Get an invoice by its ID."""
            return await invoice_service.get_invoice(invoice_id)

        @router.get(
            "/invoices",
            response_model=list[InvoiceResponse],
            response_model_exclude_none=True,
            dependencies=[require_authentication],
        )
        async def list_invoices(
            response: Response,
            invoice_status=None,
            page: int = 1,
            page_size: int = 10,
        ):
            """
            Return a page of invoices (with customer data) as JSON.

            - invoiceStatus (optional): If you omit it, you get every status. If you set it to
              PAID, PENDING, or CANCELLED, only rows with that status are counted and
              returned.
            - page (optional, default 1): Which page you want, counting from 1 (not 0).
              Must be at least 1.
            - pageSize (optional, default 10): How many invoices per page.

            Examples:

                All: GET /invoices

                Filter: GET /invoices?invoiceStatus=PENDING

                Page 2, 10 per page: GET /invoices?page=2&pageSize=10

                Combined: GET /invoices?invoiceStatus=PENDING&page=1&pageSize=10
            """
            invoices, total = await InvoiceResponse.list_invoices(
                invoice_status=invoice_status,
                page=page,
                page_size=page_size,
            )

            # Update the response headers before responding
            response.headers["X-Total-Count"] = str(total)
            response.headers["X-Page"] = str(page)
            response.headers["X-Page-Size"] = str(page_size)

            # Return a list of InvoiceResponse serialized invoices.
            return invoices

        @router.post(
            "/invoice",
            response_model=InvoiceResponse,
            status_code=201,
            dependencies=[require_authentication, require_rate_limit],
        )
        async def create_invoice(invoice_data: InvoiceRequest):
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
            new_invoice = await InvoiceRequest.process_creation_request(
                invoice_data=invoice_data,
                invoice_service=invoice_service,
            )

            # Return HTTP object which includes HTTP headers and InvoiceRequest object serialized to json
            return new_invoice

        @router.post(
            "/invoice/pay/{invoice_id}",
            response_model=InvoiceResponse,
            status_code=201,
            dependencies=[require_authentication],
        )
        async def pay_pending_invoice(
            invoice_id: Annotated[UUID, Path(description="Invoice UUID")],
            card_body: PayCardBody,
        ):
            # Calling the appropriate function from the serializer to process the payment
            payment_response = await InvoiceResponse.process_payment_request(
                invoice_id=invoice_id,
                card_body=card_body,
                invoice_service=invoice_service,
            )
            # Return an InvoiceResponse object
            return payment_response


def build_invoice_router(
    invoice_service: InvoicingService,
) -> APIRouter:
    """Return the invoice router to be used in the main.py file."""
    return InvoiceRoutes(invoice_service).router
