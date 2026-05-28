from enum import StrEnum

class Status(StrEnum):
    """Enum for the status of an invoice."""
    PAID = "PAID"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"