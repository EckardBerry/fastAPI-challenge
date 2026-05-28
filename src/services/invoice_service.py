from uuid import UUID

from src.db.invoice_manager_db import get_joined_invoice_customer_by_id
from src.exception_handlers import InvoiceRecordNotFoundError
from src.schemas.card import Card
from src.schemas.invoice_schema import InvoiceResponse
from src.schemas.model_mappers import map_db_to_invoice_response
from src.services.fake_pay_service import FakePay



class InvoicingService():
    """Service for invoicing which makes use of the FakePay service to authorize payments."""
    def __init__(self, settings):
        self.fake_pay = FakePay(settings)

    async def authorize_payment(
        self, amount, transaction_id: str, card: Card
    ) -> bool:
        """Authorize a payment wtih the FakePay service."""
        return await self.fake_pay.authorize_payment(
            amount=amount,
            transaction_id=transaction_id,
            card=card,
        )

    async def get_invoice(self, invoice_id: UUID) -> InvoiceResponse:
        """Get an invoice by its ID."""
        invoice_customer = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if invoice_customer is None:
            raise InvoiceRecordNotFoundError()

        return map_db_to_invoice_response(invoice_customer[0], invoice_customer[1])
