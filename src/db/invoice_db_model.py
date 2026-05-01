from sqlalchemy import (
    Column, Integer, String, DECIMAL, CHAR, TIMESTAMP, ForeignKey
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timezone
from sqlalchemy.orm import class_mapper

Base = declarative_base()

class InvoiceDB(Base):
    __tablename__ = "invoice"
    __table_args__ = {"schema": "invoice_management"}

    id = Column(CHAR(36), primary_key=True)  # UUID as primary key
    customer_id = Column(Integer, ForeignKey("invoice_management.customer.customer_id"), nullable=False)
    date_created = Column(TIMESTAMP, default=datetime.now(timezone.utc))
    date_modified = Column(TIMESTAMP, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    job_description = Column(String(100))
    amount = Column(DECIMAL(5, 2), nullable=False)
    invoice_status = Column(String(10), nullable=False, default="PENDING")

    # Relationship with Customer (many-to-one)
    customer = relationship("CustomerDB", back_populates="invoices")
    
    def to_dict(self):
        """Convert SQLAlchemy object to dictionary, including relationships."""
        # Use class_mapper to access columns and relationships
        data = {}
        for column in class_mapper(self.__class__).columns:
            value = getattr(self, column.key)
            data[column.key] = value
        return data
    
class CustomerDB(Base):
    __tablename__ = "customer"
    __table_args__ = {"schema": "invoice_management"}  # Use schema if applicable

    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String(50), nullable=False)
    customer_email = Column(String(50), nullable=False)

    # Relationship with InvoiceDB (one-to-many)
    invoices = relationship("InvoiceDB", back_populates="customer")
    
    def to_dict(self):
        """Convert SQLAlchemy object to dictionary, including relationships."""
        # Use class_mapper to access columns and relationships
        data = {}
        for column in class_mapper(self.__class__).columns:
            value = getattr(self, column.key)
            data[column.key] = value
        return data