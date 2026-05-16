import logging
from importlib import import_module
from typing import Optional, Self, Union
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from src.models.card import Card, MaskedCard
from src.models.enums import Status

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
    _duplicate_invoice_response: Optional["InvoiceResponse"] = PrivateAttr(
        default=None
    )

    @model_validator(mode="after")
    def _process_invoice_request(self) -> Self:
        """After parse: detect duplicate request for payment."""
        find_recent_matching_invoice = getattr(
            import_module("src.db.invoice_manager_db"), "find_recent_matching_invoice"
        )
        map_db_to_invoice_response = getattr(
            import_module("src.models.model_mappers"), "map_db_to_invoice_response"
        )

        if self.card is not None:
            self._duplicate_invoice_response = None
            return self

        recent = find_recent_matching_invoice(
            customer_id=self.customer_id,
            job_description=self.job_description,
            amount=float(self.amount),
        )
        if recent is None:
            self._duplicate_invoice_response = None
            return self

        invoice_db, customer_db = recent
        logger.info(
            "Duplicate POST suppressed: returning existing invoice %s",
            invoice_db.id,
        )
        self._duplicate_invoice_response = map_db_to_invoice_response(
            invoice_db, customer_db
        )
        return self

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, value):
        """Coerce the amount to a float and round to 2 decimal places."""
        return coerce_invoice_amount(value)

    @property
    def formatted_price(self):
        """Format the amount to 2 decimal places."""
        return "{:.2f}".format(self.amount)


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
