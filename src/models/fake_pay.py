from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from src.models.card import Card


class FakePayRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    transaction_id: UUID = Field(alias="transactionId")
    card: Card
    
    @field_serializer("transaction_id")
    def serialize_transaction_id(self, value: UUID) -> str:
        return str(value)