
from src.db.invoice_manager_db import db_health_check


class HealthCheckService:
    """Service for checking the health of the database."""
    def __init__(self, settings):
        self.settings = settings

    async def health_check(self):
        """Check the health of the database."""
        return db_health_check()
    