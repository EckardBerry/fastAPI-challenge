from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from src.models.card import Card, MaskedCard
from src.models.enums import Status


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
