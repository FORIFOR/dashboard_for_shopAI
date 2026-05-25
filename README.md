# ShopAI 稼働ダッシュボード (Prometheus + Grafana)

ShopAI の Backend / PostgreSQL / Hybrid RAG / vLLM / GPU / TTS / Staff を
管理者が一画面で確認するためのローカル監視スタック。実装方針書 (§1–§25) の成果物。

> **はじめての人へ:** セットアップは各マシンで `./setup.sh` を1回ずつ実行するだけ。
> 手順は **[SETUP.md](SETUP.md)**、概要は **[ONBOARDING.md](ONBOARDING.md)** を参照。

## このマシンと配置先 (重要)

このリポジトリは **GPU PC (192.168.0.15 / vLLM Fast Node)** 上で作成された。
監視の各コンポーネントは2台に分かれて動く:

| コンポーネント | 配置先 | 備考 |
| --- | --- | --- |
| `gpu-exporter/` (nvidia-smi → :9401) | **GPU PC 192.168.0.15** | ここで動く。systemd 常駐 |
| vLLM `/metrics` (:8000) | GPU PC 192.168.0.15 | 既存。`shopai-fast` を配信中 |
| `backend/app/observability/` | **Backend VM 192.168.0.6** | 既存 FastAPI に組み込む |
| Prometheus / Grafana / 各 exporter | **Backend VM 192.168.0.6** | `docker-compose.monitoring.yml` |

> GPU PC では Backend / PostgreSQL は動いていないため、ここで全段を通しで起動する
> ことはできない。GPU PC でローカル検証できるのは vLLM と GPU exporter の2つ
> (本セッションで検証済み — 末尾の表を参照)。

## ディレクトリ

```
shopai-dashboard/
├── docker-compose.monitoring.yml     # Backend VM: prometheus/grafana/exporters
├── .env.example                      # → .env にコピーして秘密値を設定
├── monitoring/
│   ├── prometheus/{prometheus.yml,alerts.yml}
│   └── grafana/
│       ├── provisioning/{datasources,dashboards}/*.yml
│       └── dashboards/*.json         # 4画面 (git管理。scripts/build_dashboards.py で生成)
├── backend/                          # Backend VM の FastAPI へ drop-in
│   ├── app/observability/{metrics,middleware,__init__}.py
│   ├── requirements-observability.txt
│   └── README-integration.md         # main.py/orchestrator/rag/dispatcher/health 組込手順
├── gpu-exporter/                     # GPU PC で常駐 (nvidia-smi exporter)
│   ├── gpu_exporter.py  requirements.txt
│   ├── shopai-gpu-exporter.service  install_systemd_service.sh
│   └── run_dcgm_exporter.sh          # DCGM代替 (docker+sudo)
├── sql/grafana_readonly_user.sql     # Grafana 用 read-only DBユーザ
└── scripts/
    ├── build_dashboards.py           # ダッシュボード生成
    ├── verify_vllm_metrics.sh  verify_gpu_metrics.sh
    ├── verify_backend_metrics.sh  verify_prometheus_targets.sh
```

## 段階導入 (実装方針書 §23)

### GPU PC (192.168.0.15) — ここで実施

```bash
# Phase 2: vLLM metrics 確認 (検証済み)
scripts/verify_vllm_metrics.sh 127.0.0.1:8000

# Phase 3: GPU exporter を常駐化 (systemctl は root が必要 → ! で実行)
! sudo bash ~/Project/shopai-dashboard/gpu-exporter/install_systemd_service.sh
scripts/verify_gpu_metrics.sh 127.0.0.1:9401
# ファイアウォールがある場合のみ:
! sudo ufw allow from 192.168.0.6 to any port 9401 proto tcp
```

### Backend VM (192.168.0.6) — リポジトリを転送して実施

```bash
# 0) 転送
rsync -a ~/Project/shopai-dashboard/ saiteku@192.168.0.6:~/shopai-dashboard/

# Phase 1: Backend metrics
#   backend/app/observability/ を既存 app/ に配置し README-integration.md 通り結線
pip install -r backend/requirements-observability.txt
scripts/verify_backend_metrics.sh 127.0.0.1:8080

# read-only DBユーザ作成 (Grafana の Postgres datasource 用)
! psql "postgresql://shopai@localhost:5432/shopai" -v pw="'長いパスワード'" -f sql/grafana_readonly_user.sql

# Phase 4-5: Prometheus + Grafana 起動
cp .env.example .env && $EDITOR .env       # 3つの値を設定
export SHOPAI_NETWORK=$(docker network ls --format '{{.Name}}' | grep _default | head -1)
docker compose --env-file .env -f docker-compose.monitoring.yml up -d

# Phase 4 確認: 全ターゲット UP
scripts/verify_prometheus_targets.sh localhost:9090
#   → http://192.168.0.6:9090/targets でも確認可

# Phase 5-6 確認: Grafana に4ダッシュボードが自動表示
#   → http://192.168.0.6:3000  (admin / .env の GRAFANA_ADMIN_PASSWORD)
```

設定ファイルを container 投入前に検証したい場合 (docker は sudo):
```bash
! sudo docker run --rm -v $PWD/monitoring/prometheus:/p prom/prometheus \
    promtool check config /p/prometheus.yml
! sudo docker run --rm -v $PWD/monitoring/prometheus:/p prom/prometheus \
    promtool check rules /p/alerts.yml
```

## ダッシュボード (4画面)

| UID | 画面 | 主な内容 |
| --- | --- | --- |
| `shopai-system-overview` | System Overview | Backend/DB/LLM/GPU/TTS 稼働, active model, API/LLM/RAG p95, route別件数, fallback/auth, 直近fallback(SQL) |
| `shopai-llm-gpu` | LLM & GPU | GPU util/VRAM/温度/電力/clock, vLLM running/waiting, TTFT/E2E/TPOT, KV/prefix cache, reasoning sanitize数 |
| `shopai-rag-quality` | RAG Quality | lexical/vector/fused hit率, retrieval latency, no-hit率, grounded率, top no-hit(SQL) |
| `shopai-voice-operations` | Voice & Ops | TTS成功率/latency, 再生完了率, pending staff(SQL), auth拒否(SQL) |

ダッシュボードを編集したら `python3 scripts/build_dashboards.py` で再生成し JSON をコミット。

## セキュリティ (§22)

- Grafana / Prometheus は **店舗LAN または VPN 内のみ**。インターネット非公開。
- Grafana の PostgreSQL ユーザ `shopai_dashboard` は **SELECT のみ**
  (`sql/grafana_readonly_user.sql`, `default_transaction_read_only=on`)。
- Prometheus label に `question_text` / `answer_text` / `session_id` / `chunk_id` /
  顧客情報を **入れない**。許可は route/status/node_id/model_profile/reason のみ
  (`location_id` は店舗数が少ない場合のみ)。
- 秘密値は `.env` のみ。`.gitignore` 済み。

## 仕様書からの実機補正

`vllm:prefix_cache_hits` / `vllm:prefix_cache_queries` は実機の vLLM では
**`_total` 付き** (`vllm:prefix_cache_hits_total` / `_queries_total`)。
ダッシュボードとアラートはこの実機名に合わせてある。

## 受け入れ条件 (§24) と本セッションの検証状況

| 条件 | 状態 |
| --- | --- |
| vLLM が必須 metrics を公開 | ✅ GPU PC で検証 (`verify_vllm_metrics.sh` PASS, 10/10) |
| GPU util/VRAM/温度/電力が取得可能 | ✅ nvidia-smi exporter を実機起動・検証 (RTX 5070 Ti) |
| 4ダッシュボード JSON が valid・provisioning 対応 | ✅ 生成・JSON検証済み (panels 16/16/9/8) |
| ダッシュボードの vLLM metric 名が実機と一致 | ✅ 9/9 を live endpoint と突合 |
| Prometheus/compose/Grafana provisioning が valid YAML | ✅ 全ファイル parse 確認 |
| `/metrics` が Backend で取得できる | ⬜ Backend VM で要デプロイ → `verify_backend_metrics.sh` |
| Prometheus `/targets` が全 UP | ⬜ Backend VM で compose 起動後 → `verify_prometheus_targets.sh` |
| Grafana に4画面が自動表示 | ⬜ Backend VM で Grafana 起動後 |
| TTS/Events 未実装領域は "No data" 表示 | ✅ 設計通り (NaN→非発火, パネルは No data) |
```
