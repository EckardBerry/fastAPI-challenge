from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Path, Response, HTTPException

from src.models.card import Card
from src.models.enums import Status
from src.models.invoice import InvoiceRequest, InvoiceResponse, MaskedCard
from src.config.settings import Settings
from src.services.invoice_service import InvoicingService
from src.services.health_check_service import HealthCheckService
from src.db.invoice_manager_db import (
    create_invoice_in_db,
    get_customer_by_id,
    get_joined_invoice_customer_by_id,
    update_invoice_status,
)
from src.models.model_mappers import map_db_to_invoice_response
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
            payment_successful = await fake_pay.authorize_payment(
                amount=invoice_data.amount,
                transaction_id=invoice_id,
                card=invoice_data.card
            )

            if payment_successful:
                invoice_status = "PAID"
                # Mask the card for the response
                masked_card = MaskedCard.from_card(invoice_data.card)
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

        invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
        if masked_card is not None:
            invoice_response = invoice_response.model_copy(update={"card": masked_card})
        return invoice_response

    except HTTPException:
        raise
    except Exception as error:
        print('*************************')
        print("ERROR:", repr(error))
        print('*************************')
        raise HTTPException(status_code=400, detail=str(error))


@app.post(
    "/invoice/pay/{invoice_id}",
    response_model=InvoiceResponse,
    status_code=201,
)
async def pay_pending_invoice(
    invoice_id: Annotated[UUID, Path(description="Invoice UUID")],
    card: Card,
):
    db_row = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
    if db_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No invoice found with id {invoice_id}",
        )
    invoice_db, customer_db = db_row
    if invoice_db.invoice_status != Status.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invoice status is {invoice_db.invoice_status}; "
                "only PENDING invoices can be paid"
            ),
        )

    payment_successful = await fake_pay.authorize_payment(
        amount=invoice_db.amount,
        transaction_id=str(invoice_id),
        card=card,
    )
    if not payment_successful:
        raise HTTPException(status_code=402, detail="FakePay failed")

    updated = update_invoice_status(str(invoice_id), Status.PAID.value)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"No invoice found with id {invoice_id}",
        )

    db_row = get_joined_invoice_customer_by_id(invoice_id=str(invoice_id))
    invoice_db, customer_db = db_row
    invoice_response = map_db_to_invoice_response(invoice_db, customer_db)
    masked_card = MaskedCard.from_card(card)
    return invoice_response.model_copy(update={"card": masked_card})
