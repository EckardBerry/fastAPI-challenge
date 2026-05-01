
from uuid import UUID

from fastapi import HTTPException
from src.models.invoice import InvoiceResponse, InvoiceRequest
from src.models.model_mappers import map_db_to_invoice_response
from src.db.invoice_manager_db import get_joined_invoice_customer_by_id
from src.services.fake_pay_service import FakePay
from fastapi import FastAPI

app = FastAPI()


class InvoicingService():
    def __init__(self, settings):
        self.fake_pay = FakePay(settings)
        
    async def get_invoice(self, invoice_id: UUID):
        # Returns InvoiceDB, Customer DB objects joined
        invoice_customer = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
        if invoice_customer is None:
            raise HTTPException(status_code=404, detail="No record found with this UUID")
        
        # Map to pydantic model
        invoice_response: InvoiceResponse = map_db_to_invoice_response(invoice_customer[0], invoice_customer[1])
        return 200, invoice_response.model_dump(exclude_none=True, by_alias=True)
    



