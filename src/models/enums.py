from enum import StrEnum

class Status(StrEnum):
    PAID = "PAID"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"