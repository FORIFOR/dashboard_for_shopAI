# Backend integration guide (Phase 1 — runs on Backend VM 192.168.0.6)

This directory is a **drop-in** for the existing ShopAI FastAPI backend repo.
Copy `app/observability/` into your backend's `app/` package and wire the call
sites below. Nothing here runs on the GPU PC.

## 0. Install the dependency

```bash
pip install -r requirements-observability.txt
# or add `prometheus-client>=0.20` to the backend's requirements.txt
```

## 1. Mount `/metrics` and the middleware — `app/main.py`

```python
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.observability.middleware import MetricsMiddleware

app = FastAPI(title="Shop AI Staff Backend API", version="1.0.0")

app.add_middleware(MetricsMiddleware)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

> **Multi-worker note:** `make_asgi_app()` exposes per-process counters. If you
> run gunicorn/uvicorn with `--workers > 1`, set `PROMETHEUS_MULTIPROC_DIR` to a
> writable dir and use `prometheus_client.multiprocess.MultiProcessCollector`,
> otherwise each scrape hits a random worker and counters look noisy. A single
> worker (the common ShopAI setup) needs no extra config.

Verify from the Backend VM (or from the GPU PC across the LAN):

```bash
curl http://192.168.0.6:8080/metrics | grep '^shopai_'
```

Expected:

```text
# HELP shopai_chat_requests_total Chat requests by selected route and result
# TYPE shopai_chat_requests_total counter
```

## 2. Chat route metrics — `app/orchestrator.py`

```python
import time
from app.observability.metrics import (
    CHAT_REQUESTS_TOTAL, CHAT_DURATION_SECONDS, FALLBACK_TOTAL,
)

async def process(self, request: ChatRequest, db: AsyncSession) -> ChatResponse:
    started = time.perf_counter()
    route = answer_source = "unknown"
    result = "success"
    try:
        route = await self.route_service.select_route(request)
        execution = await self.execute_route(route, request, db)
        answer_source = execution.answer_source
        if execution.answer_source == "safe_fallback":
            FALLBACK_TOTAL.labels(
                reason=execution.handoff_reason or "unknown",
                original_route=route,
            ).inc()
        return self.compose_response(execution, request)
    except Exception:
        result = "error"
        raise
    finally:
        CHAT_REQUESTS_TOTAL.labels(
            route=route, answer_source=answer_source, result=result,
        ).inc()
        CHAT_DURATION_SECONDS.labels(route=route).observe(
            time.perf_counter() - started
        )
```

## 3. RAG metrics — `app/services/rag.py`

Wrap `_lexical_search`, `_vector_search`, and `_rrf_fuse` with the
`RAG_RETRIEVAL_*` / `RAG_CHUNKS_RETURNED` instrumentation (see monitoring docs
§10). Record `retrieval_type` in `{lexical, vector, fused}` and
`result` in `{hit, miss}`.

## 4. LLM dispatcher metrics — `app/services/llm/dispatcher.py`

```python
import time
from app.observability.metrics import (
    LLM_DISPATCH_TOTAL, LLM_NODE_LATENCY_SECONDS, REASONING_SANITIZED_TOTAL,
)

async def generate(self, request: LlmGenerationRequest):
    for index, (node_id, node, api_key) in enumerate(
        self.registry.providers_for_route(request.route)
    ):
        started = time.perf_counter()
        try:
            result = await self.provider.generate(
                node_id=node_id, node=node, api_key=api_key,
                request=request, fallback_used=index > 0,
            )
            LLM_DISPATCH_TOTAL.labels(
                route=request.route, node_id=node_id,
                result="success", fallback_used=str(index > 0).lower(),
            ).inc()
            return result
        except Exception:
            LLM_DISPATCH_TOTAL.labels(
                route=request.route, node_id=node_id,
                result="failure", fallback_used=str(index > 0).lower(),
            ).inc()
        finally:
            LLM_NODE_LATENCY_SECONDS.labels(
                route=request.route, node_id=node_id,
            ).observe(time.perf_counter() - started)
    raise AllLlmProvidersUnavailable()
```

When `<think>` reasoning is stripped from the output:

```python
if cleaned_text != raw_text:
    REASONING_SANITIZED_TOTAL.labels(node_id=node_id).inc()
```

> The active vLLM node serves the model as **`shopai-fast`** and Qwen3 requires
> the `/no_think` directive (per project memory). If this counter is ever > 0,
> thinking-disable is not being applied — the RAG-quality dashboard alerts on it.

## 5. Readiness gauge — wherever `/health/ready` is implemented

```python
from app.observability.metrics import READY_COMPONENT, set_model_info

READY_COMPONENT.labels(component="database").set(1 if db_ok else 0)
READY_COMPONENT.labels(component="fast_llm").set(1 if fast_ok else 0)
READY_COMPONENT.labels(component="deep_llm").set(1 if deep_ok else 0)
READY_COMPONENT.labels(component="tts").set(1 if tts_ok else 0)
```

Publish the active model once at startup (and on profile switch):

```python
set_model_info(served_model_name="shopai-fast", profile="qwen3-8b-awq",
               node_id="fast-node")
```

## 6. TTS / Events (optional — only if implemented)

If `tts_jobs` and `events` exist, record `TTS_JOBS_TOTAL`, `TTS_DURATION_SECONDS`,
and `EVENTS_TOTAL` at the relevant call sites. If not implemented yet, leave them
untouched — the Voice & Operations dashboard shows `No data` until they emit.

## Avoiding label explosion

- Use the **matched route template** (`/devices/{id}`), never the concrete path,
  for the HTTP middleware `endpoint` label (already handled in `middleware.py`).
- Never label any metric with question text, answer text, session id, chunk id,
  or customer data. Put those in PostgreSQL and read them with the Grafana
  Postgres datasource instead (see dashboards' table panels).
