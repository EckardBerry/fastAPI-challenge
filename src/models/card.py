from pydantic import BaseModel, Field, field_validator

from src.models.regex import EXPIRY_DATE, PAN


class Card(BaseModel):
    number: str = Field(pattern=PAN)
    expiry: str = Field(pattern=EXPIRY_DATE)
    name: str

    @field_validator("number", mode="before")
    @classmethod
    def normalize_pan(cls, value):
        if isinstance(value, str):
            return "".join(c for c in value if c.isdigit())
        return value
