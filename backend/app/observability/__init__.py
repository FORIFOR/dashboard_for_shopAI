"""ShopAI observability package.

Import metrics from app.observability.metrics and mount the /metrics endpoint
with prometheus_client.make_asgi_app(). See README-integration.md.
"""

from app.observability import metrics  # noqa: F401
from app.observability.middleware import MetricsMiddleware  # noqa: F401

__all__ = ["metrics", "MetricsMiddleware"]
