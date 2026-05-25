#!/usr/bin/env python3
"""Generate the four ShopAI Grafana dashboard JSONs.

Run from the repo root:  python3 scripts/build_dashboards.py
Emits monitoring/grafana/dashboards/*.json (the git-managed artifacts).

Keeping a generator (rather than hand-editing JSON) makes the PromQL/SQL the
single source of truth and guarantees the JSON stays valid. Metric names were
verified against the live vLLM node (note: prefix-cache metrics carry the
`_total` suffix on this build).
"""

import json
import pathlib

PROM = {"type": "prometheus", "uid": "shopai-prometheus"}
PG = {"type": "postgres", "uid": "shopai-postgres"}
OUT = pathlib.Path(__file__).resolve().parent.parent / "monitoring/grafana/dashboards"

_id = 0


def _next_id():
    global _id
    _id += 1
    return _id


def prom_target(expr, legend=None, ref="A", instant=False):
    t = {"refId": ref, "expr": expr, "datasource": PROM}
    if legend is not None:
        t["legendFormat"] = legend
    if instant:
        t["instant"] = True
        t["range"] = False
    return t


def pg_target(sql, ref="A", fmt="table"):
    return {"refId": ref, "rawSql": sql, "format": fmt, "datasource": PG}


def base_field(unit=None, decimals=None, mappings=None, steps=None, color_mode="thresholds"):
    defaults = {
        "color": {"mode": color_mode},
        "mappings": mappings or [],
        "thresholds": {"mode": "absolute", "steps": steps or [{"color": "green", "value": None}]},
    }
    if unit:
        defaults["unit"] = unit
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"defaults": defaults, "overrides": []}


def stat(title, targets, gx, gy, gw=4, gh=4, unit=None, mappings=None, steps=None,
         color_mode="background", graph="none", text_mode="auto", ds=PROM):
    return {
        "id": _next_id(),
        "type": "stat",
        "title": title,
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": base_field(unit=unit, mappings=mappings, steps=steps),
        "options": {
            "colorMode": color_mode,
            "graphMode": graph,
            "justifyMode": "auto",
            "textMode": text_mode,
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "targets": targets,
    }


def timeseries(title, targets, gx, gy, gw=12, gh=8, unit=None, legend_table=False, ds=PROM):
    return {
        "id": _next_id(),
        "type": "timeseries",
        "title": title,
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {
            "defaults": {
                "custom": {"drawStyle": "line", "fillOpacity": 10, "lineWidth": 1,
                           "showPoints": "never", "spanNulls": True},
                "color": {"mode": "palette-classic"},
                "unit": unit or "short",
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
            },
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "table" if legend_table else "list",
                       "placement": "bottom", "calcs": ["lastNotNull"] if legend_table else []},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": targets,
    }


def piechart(title, targets, gx, gy, gw=8, gh=8, ds=PROM):
    return {
        "id": _next_id(),
        "type": "piechart",
        "title": title,
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right",
                               "values": ["value", "percent"]},
                    "pieType": "donut", "reduceOptions": {"calcs": ["lastNotNull"]}},
        "targets": targets,
    }


def table(title, targets, gx, gy, gw=24, gh=8, ds=PG):
    return {
        "id": _next_id(),
        "type": "table",
        "title": title,
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": []},
        "options": {"showHeader": True},
        "targets": targets,
    }


def gauge(title, targets, gx, gy, gw=4, gh=4, unit="percent", maxv=100, steps=None, ds=PROM):
    return {
        "id": _next_id(),
        "type": "gauge",
        "title": title,
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {"defaults": {
            "unit": unit, "min": 0, "max": maxv,
            "thresholds": {"mode": "absolute", "steps": steps or [
                {"color": "green", "value": None},
                {"color": "yellow", "value": maxv * 0.75},
                {"color": "red", "value": maxv * 0.9}]},
        }, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "showThresholdMarkers": True},
        "targets": targets,
    }


def row(title, gy):
    return {"id": _next_id(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": gy}, "panels": []}


def dashboard(uid, title, panels, tags, refresh="10s"):
    return {
        "uid": uid, "title": title, "tags": tags, "timezone": "browser",
        "schemaVersion": 39, "version": 1, "editable": True, "refresh": refresh,
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": []}, "annotations": {"list": []},
        "panels": panels,
    }


UP_MAP = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red", "index": 0},
    "1": {"text": "UP", "color": "green", "index": 1}}}]
UP_STEPS = [{"color": "red", "value": None}, {"color": "green", "value": 1}]


def build_system_overview():
    global _id
    _id = 0
    p = []
    p.append(stat("Backend API", [prom_target('up{job="shopai-backend"}')], 0, 0,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("PostgreSQL", [prom_target("pg_up")], 4, 0, mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("Fast LLM (vLLM)", [prom_target('up{job="shopai-vllm"}')], 8, 0,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("GPU exporter", [prom_target('up{job="shopai-gpu"}')], 12, 0,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("TTS ready", [prom_target('shopai_ready_component{component="tts"}')], 16, 0,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("DB ready", [prom_target('shopai_ready_component{component="database"}')], 20, 0,
                  mappings=UP_MAP, steps=UP_STEPS))

    p.append(table("Active model", [prom_target("shopai_llm_model_info", instant=True)],
                   0, 4, gw=12, gh=4, ds=PROM))
    p.append(stat("API p95", [prom_target(
        "histogram_quantile(0.95, sum by (le) (rate(shopai_http_request_duration_seconds_bucket[5m])))")],
        12, 4, gw=4, unit="s", color_mode="value"))
    p.append(stat("LLM p95", [prom_target(
        "histogram_quantile(0.95, sum by (le) (rate(shopai_llm_node_latency_seconds_bucket[5m])))")],
        16, 4, gw=4, unit="s", color_mode="value"))
    p.append(stat("RAG p95 (fused)", [prom_target(
        'histogram_quantile(0.95, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket{retrieval_type="fused"}[5m])))')],
        20, 4, gw=4, unit="s", color_mode="value"))

    p.append(timeseries("Requests by route (req/s)",
                        [prom_target("sum by (route) (rate(shopai_chat_requests_total[5m]))", "{{route}}")],
                        0, 8, gw=12, unit="reqps", legend_table=True))
    p.append(timeseries("Chat latency p95 by route",
                        [prom_target(
                            "histogram_quantile(0.95, sum by (le, route) (rate(shopai_chat_duration_seconds_bucket[5m])))",
                            "{{route}}")],
                        12, 8, gw=12, unit="s", legend_table=True))

    p.append(stat("Safe-fallback rate",
                  [prom_target("sum(rate(shopai_fallback_total[5m])) / clamp_min(sum(rate(shopai_chat_requests_total[5m])), 1)")],
                  0, 16, gw=6, unit="percentunit", color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.05}]))
    p.append(stat("Auth denied (1h)",
                  [prom_target("sum(increase(shopai_auth_rejections_total[1h]))")],
                  6, 16, gw=6, color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 10}]))
    p.append(timeseries("Errors & fallback (rate)",
                        [prom_target('sum(rate(shopai_chat_requests_total{result="error"}[5m]))', "chat errors", "A"),
                         prom_target("sum(rate(shopai_fallback_total[5m]))", "safe fallback", "B"),
                         prom_target("sum(rate(shopai_auth_rejections_total[5m]))", "auth denied", "C")],
                        12, 16, gw=12, unit="short", legend_table=True))

    p.append(table("Recent safe-fallback (PostgreSQL)", [pg_target(
        "SELECT created_at AS time, location_id, route, answer_source, model_used, handoff_reason "
        "FROM question_logs WHERE answer_source = 'safe_fallback' "
        "ORDER BY created_at DESC LIMIT 20;")], 0, 24, gw=24, gh=8))

    return dashboard("shopai-system-overview", "ShopAI System Overview", p,
                     ["shopai", "overview"])


def build_llm_gpu():
    global _id
    _id = 0
    p = []
    p.append(gauge("GPU Util", [prom_target("shopai_gpu_utilization_percent")], 0, 0, gw=4, gh=6))
    p.append(gauge("VRAM used %",
                   [prom_target("100 * shopai_gpu_memory_used_mib / shopai_gpu_memory_total_mib")],
                   4, 0, gw=4, gh=6,
                   steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 80},
                          {"color": "red", "value": 92}]))
    p.append(stat("GPU Temp", [prom_target("shopai_gpu_temperature_celsius")], 8, 0, gw=4, gh=6,
                  unit="celsius", color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 70},
                         {"color": "red", "value": 82}]))
    p.append(stat("Power", [prom_target("shopai_gpu_power_draw_watts")], 12, 0, gw=4, gh=6,
                  unit="watt", color_mode="value"))
    p.append(stat("GPU Clock (MHz)", [prom_target("shopai_gpu_clock_mhz")], 16, 0, gw=4, gh=6,
                  unit="short", color_mode="value"))
    p.append(stat("VRAM used (MiB)", [prom_target("shopai_gpu_memory_used_mib")], 20, 0, gw=4, gh=6,
                  unit="decmbytes", color_mode="value"))

    p.append(stat("Requests running", [prom_target("vllm:num_requests_running")], 0, 6, gw=6,
                  color_mode="value"))
    p.append(stat("Requests waiting", [prom_target("vllm:num_requests_waiting")], 6, 6, gw=6,
                  color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 3}]))
    p.append(gauge("KV cache usage", [prom_target("vllm:kv_cache_usage_perc * 100")], 12, 6, gw=6, gh=6))
    p.append(stat("Prefix cache hit",
                  [prom_target("sum(rate(vllm:prefix_cache_hits_total[5m])) / clamp_min(sum(rate(vllm:prefix_cache_queries_total[5m])), 1)")],
                  18, 6, gw=6, gh=6, unit="percentunit", color_mode="value"))

    p.append(timeseries("TTFT p50 / p95",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))", "p95", "B")],
                        0, 12, gw=12, unit="s", legend_table=True))
    p.append(timeseries("E2E request latency p50 / p95",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[5m])))", "p95", "B")],
                        12, 12, gw=12, unit="s", legend_table=True))

    p.append(timeseries("Inter-token latency p95 (TPOT)",
                        [prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:inter_token_latency_seconds_bucket[5m])))", "p95")],
                        0, 20, gw=12, unit="s"))
    p.append(timeseries("Generation token throughput (tok/s)",
                        [prom_target("sum(rate(vllm:generation_tokens_total[5m]))", "tokens/s")],
                        12, 20, gw=12, unit="short"))

    p.append(stat("Reasoning sanitized (1h)",
                  [prom_target("sum(increase(shopai_reasoning_sanitized_total[1h]))")],
                  0, 28, gw=6, color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]))
    p.append(timeseries("LLM dispatch outcomes (backend view)",
                        [prom_target("sum by (result, fallback_used) (rate(shopai_llm_dispatch_total[5m]))",
                                     "{{result}} fb={{fallback_used}}")],
                        6, 28, gw=18, unit="short", legend_table=True))
    return dashboard("shopai-llm-gpu", "ShopAI LLM & GPU", p, ["shopai", "llm", "gpu"])


def build_rag_quality():
    global _id
    _id = 0
    p = []
    p.append(stat("Lexical hit rate",
                  [prom_target('sum(rate(shopai_rag_retrieval_total{retrieval_type="lexical",result="hit"}[1h])) / clamp_min(sum(rate(shopai_rag_retrieval_total{retrieval_type="lexical"}[1h])), 1)')],
                  0, 0, gw=6, gh=4, unit="percentunit", color_mode="value"))
    p.append(stat("Vector hit rate",
                  [prom_target('sum(rate(shopai_rag_retrieval_total{retrieval_type="vector",result="hit"}[1h])) / clamp_min(sum(rate(shopai_rag_retrieval_total{retrieval_type="vector"}[1h])), 1)')],
                  6, 0, gw=6, gh=4, unit="percentunit", color_mode="value"))
    p.append(stat("Fused no-hit rate",
                  [prom_target('sum(rate(shopai_rag_retrieval_total{retrieval_type="fused",result="miss"}[1h])) / clamp_min(sum(rate(shopai_rag_retrieval_total{retrieval_type="fused"}[1h])), 1)')],
                  12, 0, gw=6, gh=4, unit="percentunit", color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.1}]))
    p.append(stat("Retrieval p95 (fused)",
                  [prom_target('histogram_quantile(0.95, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket{retrieval_type="fused"}[5m])))')],
                  18, 0, gw=6, gh=4, unit="s", color_mode="value"))

    p.append(timeseries("Retrieval outcome by type (1h increase)",
                        [prom_target("sum by (retrieval_type, result) (increase(shopai_rag_retrieval_total[1h]))",
                                     "{{retrieval_type}} {{result}}")],
                        0, 4, gw=12, unit="short", legend_table=True))
    p.append(timeseries("Retrieval latency p95 by type",
                        [prom_target("histogram_quantile(0.95, sum by (le, retrieval_type) (rate(shopai_rag_retrieval_duration_seconds_bucket[5m])))",
                                     "{{retrieval_type}}")],
                        12, 4, gw=12, unit="s", legend_table=True))

    p.append(timeseries("Chunks returned p50 by type",
                        [prom_target("histogram_quantile(0.50, sum by (le, retrieval_type) (rate(shopai_rag_chunks_returned_bucket[5m])))",
                                     "{{retrieval_type}}")],
                        0, 12, gw=12, unit="short", legend_table=True))
    p.append(stat("Grounded answer rate (1 - fallback)",
                  [prom_target("1 - (sum(rate(shopai_fallback_total[1h])) / clamp_min(sum(rate(shopai_chat_requests_total[1h])), 1))")],
                  12, 12, gw=12, gh=8, unit="percentunit", color_mode="value", graph="area"))

    p.append(table("Top no-hit questions (PostgreSQL)", [pg_target(
        "SELECT date_trunc('hour', created_at) AS time, location_id, route, count(*) AS no_hit "
        "FROM question_logs WHERE answer_source = 'safe_fallback' "
        "AND created_at >= now() - interval '24 hours' "
        "GROUP BY 1, 2, 3 ORDER BY no_hit DESC LIMIT 20;")], 0, 20, gw=24, gh=8))
    return dashboard("shopai-rag-quality", "ShopAI RAG Quality", p, ["shopai", "rag"])


def build_voice_ops():
    global _id
    _id = 0
    p = []
    p.append(stat("TTS success rate",
                  [prom_target('sum(rate(shopai_tts_jobs_total{status="completed"}[5m])) / clamp_min(sum(rate(shopai_tts_jobs_total[5m])), 1)')],
                  0, 0, gw=6, gh=4, unit="percentunit", color_mode="value"))
    p.append(stat("TTS p95 latency",
                  [prom_target("histogram_quantile(0.95, sum by (le) (rate(shopai_tts_duration_seconds_bucket[5m])))")],
                  6, 0, gw=6, gh=4, unit="s", color_mode="value"))
    p.append(stat("Playback finished rate",
                  [prom_target('sum(rate(shopai_events_total{event_type="tts_playback_finished"}[5m])) / clamp_min(sum(rate(shopai_events_total{event_type="tts_requested"}[5m])), 1)')],
                  12, 0, gw=6, gh=4, unit="percentunit", color_mode="value"))
    p.append(stat("Staff calls pending",
                  [prom_target('sum(shopai_staff_calls_total) - sum(shopai_staff_calls_total{status="resolved"})')],
                  18, 0, gw=6, gh=4, color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 1}]))

    p.append(timeseries("TTS jobs by status (rate)",
                        [prom_target("sum by (status) (rate(shopai_tts_jobs_total[5m]))", "{{status}}")],
                        0, 4, gw=12, unit="short", legend_table=True))
    p.append(timeseries("Android events by type (rate)",
                        [prom_target("sum by (event_type) (rate(shopai_events_total[5m]))", "{{event_type}}")],
                        12, 4, gw=12, unit="short", legend_table=True))

    p.append(table("Pending staff calls (PostgreSQL)", [pg_target(
        "SELECT created_at AS time, location_id, device_id, reason, status "
        "FROM staff_calls WHERE status = 'pending' ORDER BY created_at DESC LIMIT 20;")],
        0, 12, gw=24, gh=8))
    p.append(table("Recent device auth rejections (PostgreSQL)", [pg_target(
        "SELECT created_at AS time, device_id, location_id, reason "
        "FROM auth_events WHERE result = 'rejected' "
        "ORDER BY created_at DESC LIMIT 20;")], 0, 20, gw=24, gh=8))
    return dashboard("shopai-voice-operations", "ShopAI Voice & Operations", p,
                     ["shopai", "voice", "staff"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "shopai-system-overview.json": build_system_overview,
        "shopai-llm-gpu.json": build_llm_gpu,
        "shopai-rag-quality.json": build_rag_quality,
        "shopai-voice-operations.json": build_voice_ops,
    }
    for fname, fn in builders.items():
        (OUT / fname).write_text(json.dumps(fn(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {fname}")


if __name__ == "__main__":
    main()
