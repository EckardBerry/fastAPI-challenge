from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import List, Optional, Tuple

from sqlalchemy import create_engine, exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from src.config.settings import Settings
from src.db.invoice_db_model import CustomerDB, InvoiceDB


settings = Settings()

url = f'mysql+mysqlconnector://{settings.db_user}:{settings.db_password}@{settings.db_url}'  
engine = create_engine(url, echo=True)

# Create a sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Ignore duplicate POSTs that hit within this many seconds (same customer, description, amount).
DUPLICATE_INVOICE_WINDOW_SECONDS = 90


# Decorator to automatically manage the database session
def with_db_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Create session
        db = SessionLocal()
        try:
            return func(*args, db=db, **kwargs)
        finally:
            db.close()
    return wrapper


@with_db_session
def db_health_check(db=None):
    print(f">>>{url}")
    try:
        statement = exists(select(1)).select()
        check = db.execute(statement).scalar()
        return (200, {"status": "UP"}) if check else (502, {"status": "DOWN"})
    except OperationalError as error:
        # If there is a connection issue or any other operational error, catch it and return an error message
        print(f"DATABASE DOWN ERROR: {error}")
        return (502, {"status": "DOWN"})


@with_db_session
def get_customer_by_id(customer_id: int, db=None):
    """Fetch a customer by their ID."""
    return db.query(CustomerDB).filter(CustomerDB.customer_id == customer_id).first()


@with_db_session
def get_joined_invoice_customer_by_id(invoice_id: str, db=None):
    """Fetch full invoice details by ID."""
    # This query consists of InvoiceDB & CustomerDB, it will by default
    # return each separately although this is a single .join query
    invoice_customer = (
        db.query(InvoiceDB, CustomerDB)
        .join(CustomerDB, CustomerDB.customer_id == InvoiceDB.customer_id)
        .filter(InvoiceDB.id == invoice_id)
        .first()
    )

    return invoice_customer


@with_db_session
def find_recent_matching_invoice(
    customer_id: int,
    job_description: str,
    amount: float,
    within_seconds: int = DUPLICATE_INVOICE_WINDOW_SECONDS,
    db=None,
) -> Optional[Tuple[InvoiceDB, CustomerDB]]:
    """
    If the same payload was already posted recently, return that row.
    The idea is to soften accidental double-submits without a separate idempotency table.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    return (
        db.query(InvoiceDB, CustomerDB)
        .join(CustomerDB, CustomerDB.customer_id == InvoiceDB.customer_id)
        .filter(
            InvoiceDB.customer_id == customer_id,
            InvoiceDB.job_description == job_description,
            InvoiceDB.amount == amount,
            InvoiceDB.date_created >= cutoff,
        )
        .order_by(InvoiceDB.date_created.desc())
        .first()
    )


@with_db_session
def create_invoice_in_db(invoice_data, invoice_id, status, db=None):
    """Create a new invoice in the database."""
    # fields not included in 'invoice_data' are manually added, fields that
    # should not be included are removed with **invoice_data.model_dump(include=...
    new_invoice = InvoiceDB(
        id=invoice_id,
        invoice_status=status,
        **invoice_data.model_dump(
            include={"customer_id", "job_description", "amount"},
        ),
    )

    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)
    return new_invoice


@with_db_session
def update_invoice_status(invoice_id: str, status: str, db=None):
    """Update the status of an invoice in the database."""
    invoice = db.query(InvoiceDB).filter(InvoiceDB.id == invoice_id).first()
    if invoice is None:
        return False
    invoice.invoice_status = status

    db.commit()
    db.refresh(invoice)
    return True


@with_db_session
def count_invoices(
    invoice_status: Optional[str] = None,
    db=None,
) -> int:
    """Return total invoice rows, optionally restricted by status."""
    query = db.query(InvoiceDB)
    if invoice_status is not None:
        query = query.filter(InvoiceDB.invoice_status == invoice_status)

    return query.count()


@with_db_session
def list_invoices_with_customers(
    invoice_status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db=None,
) -> List[Tuple[InvoiceDB, CustomerDB]]:
    """
    Return invoice and customer rows with (optional) status filter and LIMIT/OFFSET pagination.
    """
    query = db.query(InvoiceDB, CustomerDB).join(
        CustomerDB, CustomerDB.customer_id == InvoiceDB.customer_id
    )
    if invoice_status is not None:
        query = query.filter(InvoiceDB.invoice_status == invoice_status)
    query = query.order_by(
        InvoiceDB.date_created.desc(),
        InvoiceDB.id.desc(),
    )
    
    return query.limit(limit).offset(offset).all()
