import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from src.exception_handlers.exceptions import InvalidCardExpiryError, InvalidCardNumberError
from src.models.regex import EXPIRY_DATE, PAN


class Card(BaseModel):
    """Model for a card."""
    number: str = Field(pattern=PAN)
    expiry: str = Field(pattern=EXPIRY_DATE)
    name: str

    @field_validator("number", mode="before")
    @classmethod
    def normalize_pan(cls, value):
        """Normalize the card number to exactly 16 digits."""
        if isinstance(value, str):
            return "".join(part for part in value if part.isdigit())
        return value


class PayCardBody(BaseModel):
    """Pay-invoice JSON body; validated with domain errors via parse_pay_card."""

    number: str
    expiry: str
    name: str

    @field_validator("number", mode="before")
    @classmethod
    def normalize_pan(cls, value):
        """Normalize the card number to exactly 16 digits."""
        if isinstance(value, str):
            return "".join(part for part in value if part.isdigit())
        return value

    @field_validator("expiry", mode="before")
    @classmethod
    def strip_expiry(cls, value):
        """Strip the expiry date to remove any whitespace."""
        if isinstance(value, str):
            return value.strip()
        return value


def parse_pay_card(body: PayCardBody) -> Card:
    """Normalize input and raise InvalidCardNumberError / InvalidCardExpiryError."""
    digits = "".join(part for part in body.number if part.isdigit())
    if len(digits) != 16:
        raise InvalidCardNumberError()

    expiry = body.expiry.strip()
    if not re.fullmatch(EXPIRY_DATE, expiry):
        raise InvalidCardExpiryError(
            "Expiry must be MM-YYYY with month between 01 and 12"
        )

    month, year = map(int, expiry.split("-"))
    now = datetime.now(timezone.utc)
    if (year, month) < (now.year, now.month):
        raise InvalidCardExpiryError("Card has expired")

    return Card(number=digits, expiry=expiry, name=body.name)


class MaskedCard(BaseModel):
    """Model for a masked card."""
    number: str
    expiry: str
    name: str

    @classmethod
    def from_card(cls, card: Card) -> "MaskedCard":
        """Create a masked card from a card."""
        card_number = card.number
        return cls(
            number=f"{card_number[:6]}********{card_number[-4:]}",
            expiry=card.expiry,
            name=card.name,
        )
