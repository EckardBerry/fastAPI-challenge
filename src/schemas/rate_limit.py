from fastapi import Depends, Request
from slowapi import Limiter


async def _slowapi_request_hook(request: Request) -> None:
    pass


class RateLimit:
    LIMIT = "30/minute"
    _check = None

    @classmethod
    async def enforce(cls, request: Request) -> None:
        limiter: Limiter = request.app.state.limiter
        if cls._check is None:
            cls._check = limiter.shared_limit(cls.LIMIT, scope="rate_limit")(_slowapi_request_hook)
        await cls._check(request)


require_rate_limit = Depends(RateLimit.enforce)
