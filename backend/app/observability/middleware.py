"""Starlette middleware that records per-request count and latency.

Skips the /metrics scrape endpoint so Prometheus self-scrapes do not pollute
the histograms. ``endpoint`` uses the raw path; if you have high-cardinality
path params (e.g. /devices/{id}), prefer the matched route template instead —
see README-integration.md §"Avoiding label explosion".
"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        started = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - started

            # Prefer the matched route template to bound label cardinality.
            route = request.scope.get("route")
            endpoint = getattr(route, "path", None) or request.url.path

            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)
