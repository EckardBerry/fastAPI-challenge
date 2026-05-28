from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from src.schemas.card import Card


class FakePayRequest(BaseModel):
    """Model for a FakePay request."""
    model_config = ConfigDict(populate_by_name=True)
    transaction_id: UUID = Field(alias="transactionId")
    card: Card
    
    @field_serializer("transaction_id")
    def serialize_transaction_id(self, value: UUID) -> str:
        """Serialize the transaction ID to a string."""
        return str(value)