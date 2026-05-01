from typing import Optional, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from src.models.enums import Status
from src.models.card import Card


class MaskedCard(BaseModel):
    number: str
    expiry: str
    name: str

    @classmethod
    def from_card(cls, card: Card) -> "MaskedCard":
        card_number = card.number
        return cls(
            number=f"{card_number[:6]}********{card_number[-4:]}",
            expiry=card.expiry,
            name=card.name
        )


class InvoiceRequest(BaseModel):
    model_config = ConfigDict(
        coerce_numbers_to_str=True, alias_generator=to_camel, populate_by_name=True
    )
    job_description: str
    customer_id: int
    amount: Union[str, float]
    card: Optional[Card] = Field(
        default=None,
        description="Optional. If omitted, the invoice stays PENDING.",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def round_amount(cls, value):
        if isinstance(value, bool):
            raise ValueError("amount must be a number")
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except (TypeError, ValueError):
                raise ValueError("amount must be a valid number")
        elif isinstance(value, (int, float)):
            value = float(value)
        else:
            raise ValueError("amount must be a number")
        return round(value, 2)

    @property
    def formatted_price(self):
        return "{:.2f}".format(self.amount)


class InvoiceResponse(InvoiceRequest):
    model_config = ConfigDict(
        use_enum_values=True,
        alias_generator=to_camel,
        populate_by_name=True
    )

    id: UUID
    card: Optional[MaskedCard] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    invoice_status: Status = Status.PENDING