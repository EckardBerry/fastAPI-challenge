import logging
import uuid
from typing import Annotated, Optional
from uuid import UUID

from fastapi import FastAPI, Path, Query, Response, HTTPException
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.models.card import Card
from src.models.enums import Status
from src.models.invoice import InvoiceRequest, InvoiceResponse, MaskedCard
from src.config.settings import Settings
from src.services.invoice_service import InvoicingService
from src.services.health_check_service import HealthCheckService
from src.db.invoice_manager_db import (
    count_invoices,
    create_invoice_in_db,
    get_customer_by_id,
    get_joined_invoice_customer_by_id,
    list_invoices_with_customers,
    update_invoice_status,
)
from src.models.model_mappers import map_db_to_invoice_response
from src.services.fake_pay_service import FakePay

logger = logging.getLogger(__name__)

app = FastAPI()
settings=Settings()
health_check_sevice = HealthCheckService(settings)
invoice_service = InvoicingService(settings)
fake_pay = FakePay(settings)



@app.get("/health-check")
async def health_check(response: Response):
    response.status_code, json_response = await health_check_sevice.health_check()
    return json_response

     
@app.get("/invoice/{invoice_id}")
async def get_invoice(response: Response, invoice_id: UUID = Path(...)):
    response.status_code, json_response = await invoice_service.get_invoice(invoice_id)
    return json_response


@app.get(
    "/invoices",
    response_model=list[InvoiceResponse],
    response_model_exclude_none=True,
)
async def list_invoices(
    response: Response,
    invoice_status: Annotated[
        Optional[Status],
        Query(
            alias="invoiceStatus",
            description="Filter by PAID, PENDING, or CANCELLED (omit for all)",
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="1-based page index")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            alias="pageSize",
            description="Rows per page (default 10; max 100)",
        ),
    ] = 10,
):
    """
    List invoices as InvoiceResponse objects with optional status filter.
    Results are paginated (default 10 per page); use X-Total-Count and page/pageSize to navigate.

    Examples:

        All: GET /invoices

        Filter: GET /invoices?invoiceStatus=PENDING

        Page 2, 10 per page: GET /invoices?page=2&pageSize=10

        Combined: GET /invoices?invoiceStatus=PENDING&page=1&pageSize=10
    """
    status_filter = invoice_status.value if invoice_status is not None else None
    # OFFSET grows with page so large datasets are not loaded in one query.
    offset = (page - 1) * page_size

    logger.debug(
        "Listing invoices: status_filter=%s page=%s page_size=%s offset=%s",
        status_filter,
        page,
        page_size,
        offset,
    )

    try:
        total = count_invoices(invoice_status=status_filter)
        rows = list_invoices_with_customers(
            invoice_status=status_filter,
            limit=page_size,
            offset=offset,
        )
    except OperationalError:
        logger.exception("Database unavailable while listing invoices")
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        )
    except SQLAlchemyError:
        logger.exception("Database error while listing invoices")
        raise HTTPException(
            status_code=500,
            detail="Failed to load invoices",
        )

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)

    logger.info(
        "Returned %s invoice(s) (total matching=%s, page=%s)",
        len(rows),
        total,
        page,
    )

    return [
        map_db_to_invoice_response(invoice_db, customer_db)
        for invoice_db, customer_db in rows
    ]


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
