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
         color_mode="background", graph="none", text_mode="auto", ds=PROM,
         decimals=None, desc=None):
    return {
        "id": _next_id(),
        "type": "stat",
        "title": title,
        "description": desc or "",
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": base_field(unit=unit, decimals=decimals, mappings=mappings, steps=steps),
        "options": {
            "colorMode": color_mode,
            "graphMode": graph,
            "justifyMode": "auto",
            "textMode": text_mode,
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "targets": targets,
    }


def timeseries(title, targets, gx, gy, gw=12, gh=8, unit=None, legend_table=False, ds=PROM,
               decimals=None, desc=None):
    defaults = {
        "custom": {"drawStyle": "line", "fillOpacity": 10, "lineWidth": 1,
                   "showPoints": "never", "spanNulls": True},
        "color": {"mode": "palette-classic"},
        "unit": unit or "short",
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
    }
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": _next_id(),
        "type": "timeseries",
        "title": title,
        "description": desc or "",
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {"defaults": defaults, "overrides": []},
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


def gauge(title, targets, gx, gy, gw=4, gh=4, unit="percent", maxv=100, steps=None, ds=PROM,
          decimals=0, desc=None):
    return {
        "id": _next_id(),
        "type": "gauge",
        "title": title,
        "description": desc or "",
        "datasource": ds,
        "gridPos": {"h": gh, "w": gw, "x": gx, "y": gy},
        "fieldConfig": {"defaults": {
            "unit": unit, "min": 0, "max": maxv, "decimals": decimals,
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
    ACC = "shopai_chat_requests_total"   # チャット/音声の応答数 = アクセス数
    # ── アクセス数 (大きく・全幅グラフ) ─────────────────────────────────────
    p.append(row("\U0001F4C8 コンポーネント別 アクセス数 (件/分)", 0))
    p.append(timeseries("アクセス数 推移 — バックエンド / vLLM / llama.cpp / TTS (件/分)",
                        [prom_target('sum(rate(shopai_http_requests_total{path!~"/health|/metrics"}[5m])) * 60', "バックエンド (API)", "A"),
                         prom_target('sum(rate(shopai_llm_dispatch_total{node="fast_primary"}[5m])) * 60', "vLLM (fast)", "B"),
                         prom_target('sum(rate(shopai_llm_dispatch_total{node="smart_primary"}[5m])) * 60', "llama.cpp (smart)", "C"),
                         prom_target('sum(rate(shopai_tts_first_audio_latency_seconds_count[5m])) * 60', "TTS", "D")],
                        0, 1, gw=24, gh=8, unit="short", decimals=1, legend_table=True,
                        desc="各コンポーネントへのアクセス数(件/分)。アクセスされると線が立ち上がる"))

    # ── 稼働状況 (UP/DOWN) ──────────────────────────────────────────────────
    p.append(row("\U0001F7E2 稼働状況", 9))
    p.append(stat("Backend API", [prom_target('up{job="shopai-backend"}')], 0, 10,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("PostgreSQL", [prom_target("pg_up")], 4, 10, mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("Fast LLM (vLLM)", [prom_target('up{job="shopai-vllm"}')], 8, 10,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("GPU exporter", [prom_target('up{job="shopai-gpu"}')], 12, 10,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("TTS", [prom_target('shopai_ready_component{component="tts_gateway"}')], 16, 10,
                  mappings=UP_MAP, steps=UP_STEPS))
    p.append(stat("Database", [prom_target('shopai_ready_component{component="database"}')], 20, 10,
                  mappings=UP_MAP, steps=UP_STEPS))

    # ── 稼働モデル / レイテンシ (p95) ───────────────────────────────────────
    p.append(row("\U0001F916 稼働モデル / 応答速度 (p95)", 14))
    p.append(table("稼働中モデル", [prom_target("shopai_model_info", instant=True)],
                   0, 15, gw=12, gh=4, ds=PROM))
    lat3 = [{"color": "green", "value": None}, {"color": "yellow", "value": 0.5}, {"color": "red", "value": 1.0}]
    p.append(stat("API p95", [prom_target(
        "histogram_quantile(0.95, sum by (le) (rate(shopai_http_request_duration_seconds_bucket[5m])))")],
        12, 15, gw=4, unit="s", color_mode="value", decimals=2, steps=lat3,
        desc="HTTP リクエスト全体の95パーセンタイル応答時間 (直近5分)"))
    p.append(stat("LLM p95", [prom_target(
        "histogram_quantile(0.95, sum by (le) (rate(shopai_llm_dispatch_latency_seconds_bucket[5m])))")],
        16, 15, gw=4, unit="s", color_mode="value", decimals=2, steps=lat3))
    p.append(stat("RAG p95", [prom_target(
        "histogram_quantile(0.95, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket[5m])))")],
        20, 15, gw=4, unit="s", color_mode="value", decimals=2,
        steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.3}]))

    # ── トラフィック / レイテンシ推移 ───────────────────────────────────────
    p.append(row("\U0001F4CA トラフィック / 応答速度の推移", 19))
    p.append(timeseries("ルート別リクエスト (req/s)",
                        [prom_target("sum by (route) (rate(shopai_chat_requests_total[5m]))", "{{route}}")],
                        0, 20, gw=12, unit="reqps", decimals=2, legend_table=True))
    p.append(timeseries("ルート別 応答 p95",
                        [prom_target(
                            "histogram_quantile(0.95, sum by (le, route) (rate(shopai_chat_duration_seconds_bucket[5m])))",
                            "{{route}}")],
                        12, 20, gw=12, unit="s", decimals=2, legend_table=True))

    # ── 異常 / フォールバック ───────────────────────────────────────────────
    p.append(row("\u26A0\uFE0F 異常 / フォールバック", 28))
    p.append(stat("安全フォールバック率",
                  [prom_target("(sum(rate(shopai_chat_fallback_total[5m])) or vector(0)) / clamp_min(sum(rate(shopai_chat_requests_total[5m])), 1)")],
                  0, 29, gw=6, gh=8, unit="percentunit", color_mode="value", decimals=1,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.05}, {"color": "red", "value": 0.1}],
                  desc="回答できずフォールバックした割合。高いほど RAG/モデルが答えられていない"))
    p.append(stat("認証拒否 (1h)",
                  [prom_target("sum(increase(shopai_auth_denials_total[1h])) or vector(0)")],
                  6, 29, gw=6, gh=8, color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 10}, {"color": "red", "value": 50}]))
    p.append(timeseries("エラー / フォールバック (rate)",
                        [prom_target('sum(rate(shopai_llm_dispatch_total{outcome="error"}[5m])) or vector(0)', "LLMエラー", "A"),
                         prom_target("sum(rate(shopai_chat_fallback_total[5m])) or vector(0)", "安全フォールバック", "B"),
                         prom_target("sum(rate(shopai_auth_denials_total[5m])) or vector(0)", "認証拒否", "C")],
                        12, 29, gw=12, gh=8, unit="short", decimals=2, legend_table=True))

    # ── 直近フォールバック (SQL) ────────────────────────────────────────────
    p.append(row("\U0001F4DD 直近の安全フォールバック (PostgreSQL)", 37))
    p.append(table("直近フォールバック 20件", [pg_target(
        "SELECT created_at AS time, location_id, route, answer_source, model_used, handoff_reason "
        "FROM question_logs WHERE answer_source = 'safe_fallback' "
        "ORDER BY created_at DESC LIMIT 20;")], 0, 38, gw=24, gh=8))

    return dashboard("shopai-system-overview", "ShopAI システム概要", p,
                     ["shopai", "overview"])


def build_llm_gpu():
    global _id
    _id = 0
    p = []
    DISP = "shopai_llm_dispatch_total"
    DLAT = "shopai_llm_dispatch_latency_seconds_bucket"
    # ── GPU 状態 ────────────────────────────────────────────────────────────
    p.append(row("\U0001F5A5\uFE0F GPU 状態 (RTX 5070 Ti)", 0))
    p.append(gauge("GPU 使用率", [prom_target("shopai_gpu_utilization_percent")], 0, 1, gw=4, gh=6))
    p.append(gauge("VRAM 使用率",
                   [prom_target("100 * shopai_gpu_memory_used_mib / shopai_gpu_memory_total_mib")],
                   4, 1, gw=4, gh=6,
                   steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 80}, {"color": "red", "value": 92}]))
    p.append(stat("GPU 温度", [prom_target("shopai_gpu_temperature_celsius")], 8, 1, gw=4, gh=6,
                  unit="celsius", color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 82}]))
    p.append(stat("消費電力", [prom_target("shopai_gpu_power_draw_watts")], 12, 1, gw=4, gh=6,
                  unit="watt", color_mode="value", decimals=0))
    p.append(stat("クロック (MHz)", [prom_target("shopai_gpu_clock_mhz")], 16, 1, gw=4, gh=6,
                  unit="short", color_mode="value", decimals=0))
    p.append(stat("VRAM 使用量", [prom_target("shopai_gpu_memory_used_mib * 1048576")], 20, 1, gw=4, gh=6,
                  unit="bytes", color_mode="value", decimals=1))

    # ── LLM 利用状況 (vLLM / llama.cpp 両対応・backend視点) ─────────────────────
    p.append(row("\U0001F916 LLM 利用状況 (vLLM / llama.cpp — backend視点)", 7))
    p.append(stat("LLM 呼び出し (1h)", [prom_target(f"sum(increase({DISP}[1h])) or vector(0)")],
                  0, 8, gw=6, gh=4, color_mode="value", decimals=0,
                  desc="backend が LLM を呼んだ回数 (vLLM+llama.cpp 合計)"))
    p.append(stat("成功率", [prom_target(f'(sum(increase({DISP}{{outcome="ok"}}[1h])) or vector(0)) / clamp_min(sum(increase({DISP}[1h])), 1)')],
                  6, 8, gw=6, gh=4, unit="percentunit", color_mode="value", decimals=1,
                  steps=[{"color": "red", "value": None}, {"color": "yellow", "value": 0.9}, {"color": "green", "value": 0.99}]))
    p.append(stat("エラー (1h)", [prom_target(f'sum(increase({DISP}{{outcome="error"}}[1h])) or vector(0)')],
                  12, 8, gw=6, gh=4, color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 10}]))
    p.append(stat("推論サニタイズ (1h)", [prom_target("sum(increase(shopai_reasoning_sanitized_total[1h])) or vector(0)")],
                  18, 8, gw=6, gh=4, color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
                  desc="思考過程の漏れを除去した回数。0 が理想"))
    p.append(timeseries("ノード別 LLM 呼び出し (件/分)",
                        [prom_target(f'sum(rate({DISP}{{node="fast_primary"}}[5m])) * 60', "vLLM (fast)", "A"),
                         prom_target(f'sum(rate({DISP}{{node="smart_primary"}}[5m])) * 60', "llama.cpp (smart)", "B")],
                        0, 12, gw=12, gh=8, unit="short", decimals=1, legend_table=True,
                        desc="各 LLM ノードへの呼び出し数。動いている LLM の線が立つ"))
    p.append(timeseries("ノード別 応答レイテンシ p95",
                        [prom_target(f'histogram_quantile(0.95, sum by (le) (rate({DLAT}{{node="fast_primary"}}[5m])))', "vLLM (fast)", "A"),
                         prom_target(f'histogram_quantile(0.95, sum by (le) (rate({DLAT}{{node="smart_primary"}}[5m])))', "llama.cpp (smart)", "B")],
                        12, 12, gw=12, gh=8, unit="s", decimals=2, legend_table=True))

    # ── vLLM 専用メトリクス (vLLM稼働時のみ。停止中は DOWN バナー＋No data=正常) ──
    p.append(row("\U0001F6A6 vLLM 専用メトリクス (vLLM稼働時のみ)", 20))
    p.append(stat("vLLM 稼働状態", [prom_target('up{job="shopai-vllm"}')], 0, 21, gw=24, gh=3,
                  mappings=UP_MAP, steps=UP_STEPS, color_mode="background", text_mode="value",
                  desc="DOWN=vLLM停止中。以下の vllm:* パネルが No data なのはこのため (停止中は正常)"))
    p.append(stat("処理中リクエスト", [prom_target("vllm:num_requests_running")], 0, 24, gw=6, gh=6,
                  color_mode="value", decimals=0))
    p.append(stat("待機中リクエスト", [prom_target("vllm:num_requests_waiting")], 6, 24, gw=6, gh=6,
                  color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 3}, {"color": "red", "value": 10}]))
    p.append(gauge("KV キャッシュ使用率", [prom_target("vllm:kv_cache_usage_perc * 100")], 12, 24, gw=6, gh=6))
    p.append(stat("Prefix キャッシュ命中率",
                  [prom_target("sum(rate(vllm:prefix_cache_hits_total[5m])) / clamp_min(sum(rate(vllm:prefix_cache_queries_total[5m])), 1)")],
                  18, 24, gw=6, gh=6, unit="percentunit", color_mode="value", decimals=1))

    p.append(row("\u23F1\uFE0F vLLM レイテンシ (vLLM稼働時のみ)", 30))
    p.append(timeseries("初回トークンまで TTFT (p50 / p95)",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))", "p95", "B")],
                        0, 31, gw=12, gh=8, unit="s", decimals=3, legend_table=True))
    p.append(timeseries("リクエスト全体 E2E (p50 / p95)",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:e2e_request_latency_seconds_bucket[5m])))", "p95", "B")],
                        12, 31, gw=12, gh=8, unit="s", decimals=2, legend_table=True))

    p.append(row("\U0001F4C8 vLLM スループット (vLLM稼働時のみ)", 39))
    p.append(timeseries("トークン間レイテンシ TPOT (p95)",
                        [prom_target("histogram_quantile(0.95, sum by (le) (rate(vllm:inter_token_latency_seconds_bucket[5m])))", "p95")],
                        0, 40, gw=12, gh=8, unit="s", decimals=3, legend_table=True))
    p.append(timeseries("生成トークン スループット (tok/s)",
                        [prom_target("sum(rate(vllm:generation_tokens_total[5m]))", "tokens/s")],
                        12, 40, gw=12, gh=8, unit="short", decimals=1, legend_table=True))
    return dashboard("shopai-llm-gpu", "ShopAI LLM & GPU", p, ["shopai", "llm", "gpu"])


def build_rag_quality():
    global _id
    _id = 0
    p = []
    # ── ヒット率 / 検索速度 (実機: outcome=hit/miss のハイブリッド1本) ─────────
    hit_steps = [{"color": "red", "value": None}, {"color": "yellow", "value": 0.7}, {"color": "green", "value": 0.9}]
    total_1h = "clamp_min(sum(rate(shopai_rag_retrieval_total[1h])) or vector(0), 1)"
    p.append(row("🎯 ヒット率 / 検索速度", 0))
    p.append(stat("検索ヒット率 (1h)",
                  [prom_target(f'(sum(rate(shopai_rag_retrieval_total{{outcome="hit"}}[1h])) or vector(0)) / {total_1h}')],
                  0, 1, gw=6, gh=5, unit="percentunit", color_mode="value", decimals=1, steps=hit_steps,
                  desc="ハイブリッド検索 (PGroonga+pgvector+RRF) が1件以上チャンクを返せた割合"))
    p.append(stat("ノーヒット率 (1h)",
                  [prom_target(f'(sum(rate(shopai_rag_retrieval_total{{outcome="miss"}}[1h])) or vector(0)) / {total_1h}')],
                  6, 1, gw=6, gh=5, unit="percentunit", color_mode="value", decimals=1,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.1}, {"color": "red", "value": 0.2}],
                  desc="検索しても何も当たらなかった割合。低いほど良い"))
    p.append(stat("検索 p95",
                  [prom_target("histogram_quantile(0.95, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket[5m])))")],
                  12, 1, gw=6, gh=5, unit="s", color_mode="value", decimals=2,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.3}, {"color": "red", "value": 0.5}]))
    p.append(stat("返却チャンク数 p50",
                  [prom_target("histogram_quantile(0.50, sum by (le) (rate(shopai_rag_chunks_returned_bucket[5m])))")],
                  18, 1, gw=6, gh=5, unit="short", color_mode="value", decimals=1,
                  desc="1回の検索で LLM に渡したチャンク数の中央値"))

    # ── 検索結果 / レイテンシ推移 ───────────────────────────────────────────
    p.append(row("📊 検索結果 / 速度の推移", 6))
    p.append(timeseries("結果別 検索件数 (1h)",
                        [prom_target("sum by (outcome) (increase(shopai_rag_retrieval_total[1h]))",
                                     "{{outcome}}")],
                        0, 7, gw=12, unit="short", decimals=0, legend_table=True))
    p.append(timeseries("検索レイテンシ p50 / p95",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(shopai_rag_retrieval_duration_seconds_bucket[5m])))", "p95", "B")],
                        12, 7, gw=12, unit="s", decimals=2, legend_table=True))

    # ── 根拠付与 / チャンク ─────────────────────────────────────────────────
    p.append(row("📚 根拠付与 / チャンク数", 15))
    p.append(timeseries("返却チャンク数 p50 / p95",
                        [prom_target("histogram_quantile(0.50, sum by (le) (rate(shopai_rag_chunks_returned_bucket[5m])))", "p50", "A"),
                         prom_target("histogram_quantile(0.95, sum by (le) (rate(shopai_rag_chunks_returned_bucket[5m])))", "p95", "B")],
                        0, 16, gw=12, gh=8, unit="short", decimals=1, legend_table=True))
    p.append(stat("根拠付き回答率 (1 - フォールバック)",
                  [prom_target("1 - ((sum(rate(shopai_chat_fallback_total[1h])) or vector(0)) / clamp_min(sum(rate(shopai_chat_requests_total[1h])) or vector(0), 1))")],
                  12, 16, gw=12, gh=8, unit="percentunit", color_mode="value", graph="area", decimals=1,
                  steps=[{"color": "red", "value": None}, {"color": "yellow", "value": 0.8}, {"color": "green", "value": 0.9}]))

    # ── 未ヒット質問 (SQL) ──────────────────────────────────────────────────
    p.append(row("📝 未ヒット質問 上位 (PostgreSQL)", 24))
    p.append(table("未ヒット質問 上位20 (24h)", [pg_target(
        "SELECT date_trunc('hour', created_at) AS time, location_id, route, count(*) AS no_hit "
        "FROM question_logs WHERE answer_source = 'safe_fallback' "
        "AND created_at >= now() - interval '24 hours' "
        "GROUP BY 1, 2, 3 ORDER BY no_hit DESC LIMIT 20;")], 0, 25, gw=24, gh=8))
    return dashboard("shopai-rag-quality", "ShopAI RAG 品質", p, ["shopai", "rag"])


def build_voice_ops():
    """Voice & Operations — built on the metrics the deployed backend actually
    emits (shopai_tts_* + chat/fallback/auth). The first-audio latency here is
    the TTS-stage metric shopai_tts_first_audio_latency_seconds (clause -> first
    audio chunk), which exists today; the end-to-end First-Audio KPI needs the
    not-yet-deployed shopai_voice_* metrics."""
    global _id
    _id = 0
    p = []
    FA = "shopai_tts_first_audio_latency_seconds"
    fa_steps = [{"color": "green", "value": None}, {"color": "yellow", "value": 0.7}, {"color": "red", "value": 1.0}]

    # ── TTS 初回音声 (First Audio: clause -> first audio chunk) ────────────────
    p.append(row("\U0001F50A TTS 初回音声 (First Audio)", 0))
    p.append(stat("初回音声 p50", [prom_target(f"histogram_quantile(0.50, sum by (le) (rate({FA}_bucket[5m])))")],
                  0, 1, gw=6, gh=4, unit="s", color_mode="value", decimals=2, steps=fa_steps,
                  desc="発話クリップ到着から最初の音声チャンクまで (中央値)"))
    p.append(stat("初回音声 p95", [prom_target(f"histogram_quantile(0.95, sum by (le) (rate({FA}_bucket[5m])))")],
                  6, 1, gw=6, gh=4, unit="s", color_mode="value", decimals=2, steps=fa_steps))
    p.append(stat("合成数 (1h)", [prom_target(f"sum(increase({FA}_count[1h])) or vector(0)")],
                  12, 1, gw=6, gh=4, color_mode="value", decimals=0))
    p.append(stat("TTS 失敗数 (1h)", [prom_target("sum(increase(shopai_tts_failures_total[1h])) or vector(0)")],
                  18, 1, gw=6, gh=4, color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 10}]))

    p.append(timeseries("プロバイダ別 初回音声 p95",
                        [prom_target(f"histogram_quantile(0.95, sum by (le, provider) (rate({FA}_bucket[5m])))",
                                     "{{provider}}")],
                        0, 5, gw=12, gh=8, unit="s", decimals=2, legend_table=True))
    p.append(timeseries("プロバイダ別 合成レート (件/分)",
                        [prom_target(f"sum by (provider) (rate({FA}_count[5m])) * 60", "{{provider}}")],
                        12, 5, gw=12, gh=8, unit="short", decimals=1, legend_table=True))

    # ── 初回音声レイテンシ 推移 (ストリーミング音声で実データが出る) ───────
    FAB = "shopai_tts_first_audio_latency_seconds_bucket"
    p.append(row("\U0001F4C8 初回音声レイテンシ 推移", 13))
    p.append(timeseries("初回音声 p50 / p95 / p99 推移",
                        [prom_target(f"histogram_quantile(0.50, sum by (le) (rate({FAB}[5m])))", "p50", "A"),
                         prom_target(f"histogram_quantile(0.95, sum by (le) (rate({FAB}[5m])))", "p95", "B"),
                         prom_target(f"histogram_quantile(0.99, sum by (le) (rate({FAB}[5m])))", "p99", "C")],
                        0, 14, gw=24, gh=8, unit="s", decimals=2, legend_table=True))
    # ── チャット運用 (ルート / フォールバック / 認証) ──────────────────────────
    p.append(row("\U0001F91D チャット運用 (ルート / フォールバック)", 22))
    p.append(timeseries("ルート別 リクエスト (req/s)",
                        [prom_target("sum by (route) (rate(shopai_chat_requests_total[5m]))", "{{route}}")],
                        0, 23, gw=12, gh=8, unit="reqps", decimals=2, legend_table=True))
    p.append(timeseries("回答ソース別 リクエスト (req/s)",
                        [prom_target("sum by (answer_source) (rate(shopai_chat_requests_total[5m]))", "{{answer_source}}")],
                        12, 23, gw=12, gh=8, unit="reqps", decimals=2, legend_table=True))
    p.append(timeseries("フォールバック理由別 (1h 増分)",
                        [prom_target("sum by (reason) (increase(shopai_chat_fallback_total[1h]))", "{{reason}}")],
                        0, 31, gw=12, gh=8, unit="short", decimals=0, legend_table=True))
    p.append(stat("認証拒否 (1h)", [prom_target("sum(increase(shopai_auth_denials_total[1h])) or vector(0)")],
                  12, 31, gw=6, gh=8, color_mode="value", decimals=0,
                  steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 10}, {"color": "red", "value": 50}]))
    p.append(stat("フォールバック総数 (1h)", [prom_target("sum(increase(shopai_chat_fallback_total[1h])) or vector(0)")],
                  18, 31, gw=6, gh=8, color_mode="value", decimals=0))

    # ── スタッフ対応 / 認証 (PostgreSQL) ───────────────────────────────────────
    p.append(row("\U0001F4DD スタッフ対応 / 認証 (PostgreSQL)", 39))
    p.append(table("保留中スタッフ呼び出し", [pg_target(
        "SELECT created_at AS time, location_id, device_id, reason, status "
        "FROM staff_calls WHERE status = 'pending' ORDER BY created_at DESC LIMIT 20;")],
        0, 40, gw=24, gh=8))
    p.append(table("直近の認証拒否", [pg_target(
        "SELECT created_at AS time, device_id, location_id, reason "
        "FROM auth_events WHERE result = 'rejected' "
        "ORDER BY created_at DESC LIMIT 20;")], 0, 48, gw=24, gh=8))
    return dashboard("shopai-voice-operations", "ShopAI Voice & Operations", p,
                     ["shopai", "voice", "staff"])


def build_service_health():
    """Health / uptime screen — "is everything up?" at a glance.

    Pure Prometheus (no PostgreSQL), driven by blackbox probe_success + the
    node-exporter/cadvisor agents. Pairs with prometheus.health.yml. This is the
    landing dashboard for the stand-alone health stack (docker-compose.health.yml).
    """
    global _id
    _id = 0
    p = []

    BV, GP = "192.168.0.6", "192.168.0.15"   # backend-vm, gpu-pc

    # ── headline: is anything down right now? ───────────────────────────────
    p.append(row("🟢 全体ステータス", 0))
    p.append(stat("全死活チェック (1つでも赤ければ要対応)",
                  [prom_target("min(probe_success)")], 0, 1, gw=12, gh=4,
                  mappings=UP_MAP, steps=UP_STEPS, text_mode="value"))
    p.append(stat("ダウン中の数",
                  [prom_target("count(probe_success == 0) or vector(0)")],
                  12, 1, gw=4, gh=4, color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]))
    p.append(stat("発火中アラート",
                  [prom_target('count(ALERTS{alertstate="firing"}) or vector(0)')],
                  16, 1, gw=4, gh=4, color_mode="value",
                  steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]))
    p.append(timeseries("アクセス数 推移 (件/分)",
                        [prom_target("sum(rate(shopai_chat_requests_total[5m])) * 60", "件/分")],
                        20, 1, gw=4, gh=4, unit="short", decimals=1,
                        desc="チャット/音声アクセスの推移 (件/分)"))

    # ── per-service liveness grid (green=UP / red=DOWN) ─────────────────────
    p.append(row("サービス別 死活 (UP / DOWN)", 5))
    grid = [
        ("Backend VM (ping)",   f'probe_success{{job="ping",instance="{BV}"}}'),
        ("GPU PC (ping)",       f'probe_success{{job="ping",instance="{GP}"}}'),
        ("Backend API :8080",   f'probe_success{{job="tcp-probe",instance="{BV}:8080"}}'),
        ("PostgreSQL :5432",    f'probe_success{{job="tcp-probe",instance="{BV}:5432"}}'),
        ("vLLM :8000",          f'probe_success{{job="tcp-probe",instance="{GP}:8000"}}'),
        ("GPU exporter :9401",  f'probe_success{{job="tcp-probe",instance="{GP}:9401"}}'),
        ("vLLM /health",        f'probe_success{{job="http-probe",instance="http://{GP}:8000/health"}}'),
        ("Backend /health",     f'probe_success{{job="http-probe",instance="http://{BV}:8080/health"}}'),
    ]
    for i, (title, expr) in enumerate(grid):
        p.append(stat(title, [prom_target(expr)], (i % 6) * 4, 6 + (i // 6) * 4,
                      gw=4, gh=4, mappings=UP_MAP, steps=UP_STEPS))

    # ── host vitals ──────────────────────────────────────────────────────────
    p.append(row("ホスト リソース (Backend VM / GPU PC)", 14))
    p.append(timeseries("CPU 使用率 (%)",
                        [prom_target("100 - (avg by (host) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
                                     "{{host}}")],
                        0, 15, gw=8, gh=6, unit="percent", legend_table=True))
    p.append(timeseries("メモリ使用率 (%)",
                        [prom_target("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
                                     "{{host}}")],
                        8, 15, gw=8, gh=6, unit="percent", legend_table=True))
    p.append(timeseries("ディスク使用率 (% / ルート)",
                        [prom_target('100 * (1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"})',
                                     "{{host}}")],
                        16, 15, gw=8, gh=6, unit="percent", legend_table=True))

    # ── uptime / reboot detection + probe latency ───────────────────────────
    p.append(row("稼働時間 / 応答時間", 21))
    p.append(stat("Backend VM 稼働時間",
                  [prom_target('node_time_seconds{host="backend-vm"} - node_boot_time_seconds{host="backend-vm"}')],
                  0, 22, gw=6, gh=4, unit="s", color_mode="value"))
    p.append(stat("GPU PC 稼働時間",
                  [prom_target('node_time_seconds{host="gpu-pc"} - node_boot_time_seconds{host="gpu-pc"}')],
                  6, 22, gw=6, gh=4, unit="s", color_mode="value"))
    p.append(timeseries("外形応答時間 (probe_duration)",
                        [prom_target("probe_duration_seconds", "{{instance}}")],
                        12, 22, gw=12, gh=6, unit="s", legend_table=True))

    # ── container states ─────────────────────────────────────────────────────
    p.append(row("コンテナ稼働 (cadvisor)", 28))
    p.append(stat("Backend VM コンテナ数",
                  [prom_target('count(container_last_seen{host="backend-vm",name=~".+"})')],
                  0, 29, gw=6, gh=4, color_mode="value"))
    p.append(stat("GPU PC コンテナ数",
                  [prom_target('count(container_last_seen{host="gpu-pc",name=~".+"})')],
                  6, 29, gw=6, gh=4, color_mode="value"))
    p.append(timeseries("コンテナ CPU 使用率 上位 (%)",
                        [prom_target('topk(10, sum by (name) (rate(container_cpu_usage_seconds_total{name=~".+"}[5m])) * 100)',
                                     "{{name}}")],
                        12, 29, gw=12, gh=6, unit="percent", legend_table=True))

    # ── 端末 (タブレット/PC) 死活: devices.json に IP を追記すると表示 ──────────
    p.append(row("📱 端末 死活 (devices.json に IP を追加すると表示)", 35))
    p.append(stat("端末 UP/DOWN",
                  [prom_target('probe_success{job="device-ping"}', "{{name}}")],
                  0, 36, gw=12, gh=6, mappings=UP_MAP, steps=UP_STEPS, color_mode="background",
                  desc="ICMP ping。Android タブレットは省電力スリープで落ちて見えることがある (要注意)"))
    p.append(timeseries("端末 応答時間 (ping)",
                        [prom_target('probe_duration_seconds{job="device-ping"}', "{{name}}")],
                        12, 36, gw=12, gh=6, unit="s", decimals=3, legend_table=True))

    return dashboard("shopai-service-health", "ShopAI Service Health", p,
                     ["shopai", "health", "uptime"], refresh="30s")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "shopai-service-health.json": build_service_health,
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
