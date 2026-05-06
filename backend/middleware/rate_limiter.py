from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


# Key function: rate limit per client IP
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Returns 429 with a Retry-After header.
    The client should back off for 1 second and retry.
    """
    return JSONResponse(
        status_code=429,
        headers={
            "Retry-After": "1",
            "X-RateLimit-Limit": str(exc.limit),
        },
        content={
            "error": "rate_limit_exceeded",
            "message": f"Too many requests. Limit: {exc.limit}. Retry after 1 second.",
            "retry_after_seconds": 1,
        }
    )
