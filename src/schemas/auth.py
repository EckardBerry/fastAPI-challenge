from typing import Annotated, Self

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from src.config.settings import Settings


class AuthenticatedRequest(BaseModel):
    """API key extracted from the request and validated before the endpoint runs."""

    model_config = ConfigDict(frozen=True)

    api_key: str

    @classmethod
    async def verify(
        cls,
        x_api_key: Annotated[str, Header(alias="X-API-Key")],
    ) -> Self:
        """Verify the API key."""
        settings = Settings()
        if x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return cls(api_key=x_api_key)


# Before handler: dependencies=[require_authentication] on the route decorator.
# Depends(...) calls verify() before the endpoint body runs.
require_authentication = Depends(AuthenticatedRequest.verify)
