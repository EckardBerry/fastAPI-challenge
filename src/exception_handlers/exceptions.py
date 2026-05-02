"""Domain exceptions for the API and registration of FastAPI handlers that map them to HTTP."""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for application errors."""

    status_code: int = 500

    def __init__(self, detail: str) -> None:
        self.detail = detail
        self.status_code = type(self).status_code
        super().__init__(detail)


class CustomerNotFoundError(AppError):
    """Used when GET /customer/id finds no record."""
    status_code = 404

    def __init__(self, customer_id: int) -> None:
        super().__init__(f"Customer with id {customer_id} not found")


class InvoiceNotFoundError(AppError):
    """Used when GET /invoice/id finds no record."""
    status_code = 404

    def __init__(self, invoice_id: str, *, detail: str | None = None) -> None:
        super().__init__(
            detail if detail is not None else f"No invoice found with id {invoice_id}"
        )


class InvoiceRecordNotFoundError(AppError):
    """Used when GET /invoice/id finds no row."""

    status_code = 404

    def __init__(self) -> None:
        super().__init__("No record found with this UUID")


class FakePayFailedError(AppError):
    """Used when FakePay fails to authorize a payment."""
    status_code = 402

    def __init__(self, detail: str = "FakePay failed") -> None:
        super().__init__(detail)


class InvoiceNotPendingError(AppError):
    """Used when trying to pay a non-PENDING invoice."""
    status_code = 409

    def __init__(self, current_status: str) -> None:
        super().__init__(
            f"Invoice status is {current_status}; only PENDING invoices can be paid"
        )


class DatabaseUnavailableError(AppError):
    """Used when the database is temporarily unavailable."""
    status_code = 503

    def __init__(self, detail: str = "Database temporarily unavailable") -> None:
        super().__init__(detail)


class DatabaseOperationError(AppError):
    """Used when a database operation fails."""
    status_code = 500

    def __init__(self, detail: str = "Database operation failed") -> None:
        super().__init__(detail)


class BadRequestError(AppError):
    """Used when the request is invalid."""
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class InvalidCardNumberError(AppError):
    """PAN must normalize to exactly 16 digits (used when paying an invoice)."""

    status_code = 400

    def __init__(self) -> None:
        super().__init__(
            "Card number must contain exactly 16 digits "
            "(spaces and punctuation are ignored)"
        )


class InvalidCardExpiryError(AppError):
    """Expiry must be MM-YYYY and the card must not be expired (pay endpoint)."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Handle AppError exceptions and return a JSON response with the error details."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def register_exception_handlers(app) -> None:
    """Register exception handlers for the app to use them in the main.py file."""
    app.add_exception_handler(AppError, app_error_handler)
