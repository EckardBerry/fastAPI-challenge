
from src.db.invoice_manager_db import db_health_check


class HealthCheckService:
    def __init__(self, settings):
        self.settings = settings

    async def health_check(self):
        return db_health_check()
    