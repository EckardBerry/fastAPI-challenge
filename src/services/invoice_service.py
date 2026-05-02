import uuid
from uuid import UUID

from src.db.invoice_manager_db import (
    create_invoice_in_db,
    get_customer_by_id,
    get_joined_invoice_customer_by_id,
)
from src.exception_handlers import (
    CustomerNotFoundError,
    FakePayFailedError,
    InvoiceRecordNotFoundError,
)
from src.models.card import Card, MaskedCard
from src.models.enums import Status
from src.models.invoice import InvoiceRequest, InvoiceResponse
from src.models.model_mappers import map_db_to_invoice_response
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

    async def get_invoice(self, invoice_id: UUID):
        """Get an invoice by its ID."""
        invoice_customer = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if invoice_customer is None:
            raise InvoiceRecordNotFoundError()

        invoice_response: InvoiceResponse = map_db_to_invoice_response(
            invoice_customer[0], invoice_customer[1]
        )
        return 200, invoice_response.model_dump(exclude_none=True, by_alias=True)

    async def execute_invoice_creation(self, invoice_data: InvoiceRequest) -> InvoiceResponse:
        """Persist a new invoice and optionally charge via FakePay; return InvoiceResponse."""
        customer = get_customer_by_id(invoice_data.customer_id)
        if customer is None:
            raise CustomerNotFoundError(invoice_data.customer_id)

        invoice_id = str(uuid.uuid4())
        invoice_status = Status.PENDING
        masked_card = None

        if invoice_data.card:
            payment_successful = await self.authorize_payment(
                amount=invoice_data.amount,
                transaction_id=invoice_id,
                card=invoice_data.card,
            )
            if payment_successful:
                invoice_status = Status.PAID
                masked_card = MaskedCard.from_card(invoice_data.card)
            else:
                raise FakePayFailedError()

        create_invoice_in_db(
            invoice_data=invoice_data,
            invoice_id=invoice_id,
            status=invoice_status,
        )

        db_data = get_joined_invoice_customer_by_id(invoice_id=invoice_id)
        invoice_db, customer_db = db_data

        invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
        if masked_card is not None:
            invoice_response = invoice_response.model_copy(update={"card": masked_card})
        return invoice_response
