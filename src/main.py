from uuid import UUID
from fastapi import FastAPI, Path, Query, Response, HTTPException

from src.models.invoice import InvoiceRequest, InvoiceResponse
from src.config.settings import Settings
from src.services.invoice_service import InvoicingService
from src.services.health_check_service import HealthCheckService
from src.db.invoice_manager_db import (
    create_invoice_in_db,
    get_customer_by_id,
    get_joined_invoice_customer_by_id,
)
from src.services.fake_pay_service import FakePay
import uuid


app=FastAPI()
settings=Settings()
health_check_sevice = HealthCheckService(settings)
invoice_service = InvoicingService(settings)
fake_pay = FakePay(settings)



@app.get("/health-check")
async def health_check(response: Response):
    response.status_code, json_response = await health_check_sevice.health_check()
    return json_response

     
@app.get("/invoice/{invoice_id}")
async def get_invoice(response: Response, invoice_id:UUID = Path(...)):
     response.status_code, json_response = await invoice_service.get_invoice(invoice_id)
     return json_response


@app.post("/invoice_create/", response_model=InvoiceResponse, status_code=201)
async def create_new_invoice(invoice_data: InvoiceRequest):
    try:
        customer = get_customer_by_id(invoice_data.customer_id)
        if customer is None:
            raise HTTPException(
                status_code=404,
                detail=f"Customer with id {invoice_data.customer_id} not found",
            )

        # Generate the ID first to sync with FakePay Transaction ID
        invoice_id = str(uuid.uuid4())
        invoice_status = "PENDING"
        masked_card = None

        # if Card is provided, take care of payment
        if invoice_data.card:
            # Call FakePay asynchronously
            payment_successful = await fake_pay.authorize(
                amount=invoice_data.amount,
                transaction_id=invoice_id,
                card=invoice_data.card
            )

            if payment_successful:
                invoice_status = "PAID"
                
                # Mask the card for the response
                num = invoice_data.card.number
                masked_card = {
                    "number": f"{num[:6]}********{num[-4:]}",
                    "expiry": invoice_data.card.expiry,
                    "name": invoice_data.card.name
                }
            else:
                raise HTTPException(status_code=402, detail="FakePay failed")

        # Save new invoice to db
        new_invoice = create_invoice_in_db(
            invoice_data=invoice_data, 
            invoice_id=invoice_id, 
            status=invoice_status
        )

        db_data = get_joined_invoice_customer_by_id(invoice_id=invoice_id)
        invoice_db, customer_db = db_data

        # Return json object
        return {
            "id": invoice_db.id,
            "jobDescription": invoice_db.job_description,
            "customerId": invoice_db.customer_id,
            "amount": float(invoice_db.amount),
            "card": masked_card,
            "customerName": customer_db.customer_name,
            "customerEmail": customer_db.customer_email,
            "invoiceStatus": invoice_db.invoice_status
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
