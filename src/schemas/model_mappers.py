from src.db.invoice_db_model import CustomerDB, InvoiceDB


def map_db_to_invoice_response(invoice: InvoiceDB, customer: CustomerDB):
    """Map a database invoice and customer to an InvoiceResponse."""
    # Import here to avoid circular import
    from src.schemas.invoice_schema import InvoiceResponse

    customer_dict = customer.to_dict()
    # Need to remove id to avoid duplicate kwarg population
    customer_dict.pop("customer_id")
    response = InvoiceResponse(
        # Dump feilds as kwargs
        **customer_dict,
        **invoice.to_dict(),
    )
    return response
