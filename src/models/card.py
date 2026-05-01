from pydantic import BaseModel, Field

from src.models.regex import EXPIRY_DATE, PAN

class Card(BaseModel):
    number: str = Field(pattern=PAN)
    expiry: str = Field(pattern=EXPIRY_DATE)
    name: str
    