from typing import Optional, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

from src.models.enums import Status

class InvoiceRequest(BaseModel):
    model_config = ConfigDict(
        coerce_numbers_to_str=True, alias_generator=to_camel,  populate_by_name=True
    )
    job_description: str
    customer_id: int
    amount: Union[str, float]
    
    @field_validator("amount", mode="before")
    def round_amount(cls, v):
        return round(v, 2)

    @property
    def formatted_price(self):
        return "{:.2f}".format(self.amount)
    
class InvoiceResponse(InvoiceRequest):
    model_config = ConfigDict(use_enum_values=True, alias_generator=to_camel,  populate_by_name=True)
    id: UUID
    customer_name: Optional[str] = None
    customer_email:  Optional[str] = None
    invoice_status: Status = Status.PENDING
    