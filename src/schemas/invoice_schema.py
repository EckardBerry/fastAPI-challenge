import logging
import uuid
from typing import TYPE_CHECKING, Optional, Self, Union, Annotated, Any
from fastapi import APIRouter, Path, Query, Request, Response
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic.alias_generators import to_camel
from src.db.invoice_manager_db import (
    count_invoices,
    list_invoices_with_customers,
)

from src.db.invoice_manager_db import (
    create_invoice_in_db,
    find_recent_matching_invoice,
    get_customer_by_id,
    get_joined_invoice_customer_by_id,
    update_invoice_status,
)
from src.exception_handlers.exceptions import (
    CustomerNotFoundError,
    FakePayFailedError,
    InvoiceNotFoundError,
    InvoiceNotPendingError,
    DatabaseUnavailableError,
    DatabaseOperationError,
)
from src.schemas.card import Card, MaskedCard, PayCardBody, parse_pay_card
from src.schemas.enums import Status
from src.schemas.model_mappers import map_db_to_invoice_response

if TYPE_CHECKING:
    from src.services.invoice_service import InvoicingService

logger = logging.getLogger(__name__)


def coerce_invoice_amount(value):
    """Shared coercion for request/response 'amount' fields."""
    if isinstance(value, bool):
        raise ValueError("amount must be a number")
    if isinstance(value, str):
        try:
            coerced = float(value.strip())
        except (TypeError, ValueError):
            raise ValueError("amount must be a valid number")
        return round(coerced, 2)
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        raise ValueError("amount must be a number")


class InvoiceRequest(BaseModel):
    """Base model for invoice request."""

    model_config = ConfigDict(
        coerce_numbers_to_str=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )
    job_description: str
    customer_id: int
    amount: Union[str, float]
    card: Optional[Card] = Field(
        default=None,
        description="Optional. If omitted, no payment is attempted and status stays PENDING.",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, value):
        """Coerce the amount to a float and round to 2 decimal places."""
        return coerce_invoice_amount(value)

    @property
    def formatted_price(self):
        """Format the amount to 2 decimal places."""
        return "{:.2f}".format(self.amount)

    @classmethod
    async def process_creation_request(
        cls,
        invoice_data: Self,
        invoice_service: "InvoicingService",
    ) -> "InvoiceResponse":
        """Create flow: dedupe, optional payment, persist, build response."""
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

        customer = get_customer_by_id(invoice_data.customer_id)
        if not customer:
            raise CustomerNotFoundError(customer_id=invoice_data.customer_id)

        invoice_id = str(uuid.uuid4())
        invoice_status = Status.PENDING
        masked_card = None

        if invoice_data.card:
            payment_successful = await invoice_service.authorize_payment(
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

        database_record = get_joined_invoice_customer_by_id(invoice_id=invoice_id)
        if database_record is None:
            raise InvoiceNotFoundError(invoice_id)

        invoice_db, customer_db = database_record
        invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
        if masked_card is not None:
            invoice_response = invoice_response.model_copy(update={"card": masked_card})
        return invoice_response


class InvoiceResponse(BaseModel):
    """API invoice shape."""

    model_config = ConfigDict(
        use_enum_values=True,
        alias_generator=to_camel,
        populate_by_name=True,
        coerce_numbers_to_str=True,
    )
    job_description: str
    customer_id: int
    amount: Union[str, float]
    card: Optional[MaskedCard] = None
    id: UUID
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    invoice_status: Status = Status.PENDING

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, value):
        """Coerce the amount to a float and round to 2 decimal places."""
        return coerce_invoice_amount(value)

    @classmethod
    async def process_payment_request(
        cls,
        invoice_id: UUID,
        card_body: PayCardBody,
        invoice_service: "InvoicingService",
    ) -> "InvoiceResponse":
        """Pay flow: validate card, load invoice, charge, mark PAID, build response."""
        card = parse_pay_card(card_body)

        database_record = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if database_record is None:
            raise InvoiceNotFoundError(str(invoice_id))

        invoice_db, customer_db = database_record
        if invoice_db.invoice_status != Status.PENDING.value:
            raise InvoiceNotPendingError(invoice_db.invoice_status)

        payment_successful = await invoice_service.authorize_payment(
            amount=invoice_db.amount,
            transaction_id=str(invoice_id),
            card=card,
        )
        if not payment_successful:
            raise FakePayFailedError()

        # Payment successful? Mark the invoice as PAID
        updated = update_invoice_status(str(invoice_id), Status.PAID)
        if not updated:
            raise InvoiceNotFoundError(str(invoice_id))

        updated_invoice = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if updated_invoice is None:
            raise InvoiceNotFoundError(str(invoice_id))

        invoice_db, customer_db = updated_invoice
        # Map to an InvoiceResponse object
        invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
        return invoice_response.model_copy(update={"card": MaskedCard.from_card(card)})

    @classmethod
    async def list_invoices(
        cls,
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
    ) -> tuple[list[Any], int]:
        """List all invoices."""
        status_filter = invoice_status if invoice_status is not None else None
        offset = (int(page) - 1) * int(page_size)

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

        # Return a list of InvoiceResponse serialized invoices and the total
        return [
            map_db_to_invoice_response(invoice_db, customer_db)
            for invoice_db, customer_db in records
        ], total
