"""ShopAI backend Prometheus metric definitions.

This module is the single source of truth for the metric contract the Grafana
dashboards depend on. Do NOT put high-cardinality values (question_text,
answer_text, session_id, chunk_id, customer data) into labels — keep labels to
route / status / node_id / model_profile / reason / location_id (only if the
number of stores is small). See monitoring docs §22.2.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

HTTP_REQUESTS_TOTAL = Counter(
    "shopai_http_requests_total",
    "HTTP request count",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "shopai_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

CHAT_REQUESTS_TOTAL = Counter(
    "shopai_chat_requests_total",
    "Chat requests by selected route and result",
    ["route", "answer_source", "result"],
)

CHAT_DURATION_SECONDS = Histogram(
    "shopai_chat_duration_seconds",
    "End-to-end chat latency",
    ["route"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

FALLBACK_TOTAL = Counter(
    "shopai_fallback_total",
    "Fallback responses",
    ["reason", "original_route"],
)

AUTH_REJECTIONS_TOTAL = Counter(
    "shopai_auth_rejections_total",
    "Rejected device authentication or scope checks",
    ["reason"],
)

RAG_RETRIEVAL_TOTAL = Counter(
    "shopai_rag_retrieval_total",
    "RAG retrieval outcome",
    ["retrieval_type", "result"],
)

RAG_RETRIEVAL_DURATION_SECONDS = Histogram(
    "shopai_rag_retrieval_duration_seconds",
    "RAG retrieval latency",
    ["retrieval_type"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)

RAG_CHUNKS_RETURNED = Histogram(
    "shopai_rag_chunks_returned",
    "Retrieved RAG chunks count",
    ["retrieval_type"],
    buckets=(0, 1, 2, 3, 5, 10, 20),
)

STAFF_CALLS_TOTAL = Counter(
    "shopai_staff_calls_total",
    "Staff calls",
    ["status"],
)

LLM_DISPATCH_TOTAL = Counter(
    "shopai_llm_dispatch_total",
    "LLM node invocation outcomes",
    ["route", "node_id", "result", "fallback_used"],
)

LLM_NODE_LATENCY_SECONDS = Histogram(
    "shopai_llm_node_latency_seconds",
    "LLM provider request latency observed by backend",
    ["route", "node_id"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30),
)

LLM_MODEL_INFO = Info(
    "shopai_llm_model",
    "Current configured LLM model information",
)

REASONING_SANITIZED_TOTAL = Counter(
    "shopai_reasoning_sanitized_total",
    "Number of reasoning tags stripped from LLM output",
    ["node_id"],
)

TTS_JOBS_TOTAL = Counter(
    "shopai_tts_jobs_total",
    "TTS jobs by result",
    ["provider", "status", "cache_hit"],
)

TTS_DURATION_SECONDS = Histogram(
    "shopai_tts_duration_seconds",
    "TTS synthesis latency",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8),
)

EVENTS_TOTAL = Counter(
    "shopai_events_total",
    "Android events received",
    ["event_type"],
)

READY_COMPONENT = Gauge(
    "shopai_ready_component",
    "Readiness of dependent services (1=ready, 0=unavailable)",
    ["component"],
)


def set_model_info(served_model_name: str, profile: str, node_id: str) -> None:
    """Publish the active model as labels on shopai_llm_model_info.

    Call once at startup and again whenever the active profile switches so the
    System Overview / LLM dashboards can show ``Active Model``.
    """
    LLM_MODEL_INFO.info(
        {
            "served_model_name": served_model_name,
            "profile": profile,
            "node_id": node_id,
        }
    )
