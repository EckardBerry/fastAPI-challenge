from fastapi import FastAPI, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config.settings import Settings
from src.exception_handlers import register_exception_handlers
from src.routers.invoice_routes import build_invoice_router
from src.services.health_check_service import HealthCheckService
from src.services.invoice_service import InvoicingService

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)

settings = Settings()
health_check_sevice = HealthCheckService(settings)
invoice_service = InvoicingService(settings)


@app.get("/health-check")
async def health_check(response: Response):
    response.status_code, json_response = await health_check_sevice.health_check()
    return json_response


# All invoice routes/endpoints are grouped together in routers/invoice_routes.py file.
app.include_router(build_invoice_router(invoice_service, limiter))
