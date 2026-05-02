from pydantic import BaseModel, Field, field_validator

from src.models.regex import EXPIRY_DATE, PAN


class Card(BaseModel):
    """Model for a card."""
    number: str = Field(pattern=PAN)
    expiry: str = Field(pattern=EXPIRY_DATE)
    name: str

    @field_validator("number", mode="before")
    @classmethod
    def normalize_pan(cls, value):
        if isinstance(value, str):
            return "".join(c for c in value if c.isdigit())
        return value


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
