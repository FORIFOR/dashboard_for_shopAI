# ShopAI 稼働ダッシュボード — オンボーディング

ShopAI の Backend / PostgreSQL / Hybrid RAG / vLLM / GPU / TTS / Staff を
**Prometheus + Grafana** で可視化する監視スタックです。このガイドだけで、
だれでもゼロから構築できます。

## 全体像

```
Android → Backend(FastAPI :8080) → PostgreSQL / vLLM(:8000) / TTS
                  │ /metrics                       │ /metrics      │ GPU exporter(:9401)
                  └──────────────┬─────────────────┴───────────────┘
                          Prometheus(:9090) → Grafana(:3000) 4ダッシュボード
```

2台にまたがります:
- **GPU PC(192.168.0.15)** … vLLM と GPU exporter
- **Backend VM(192.168.0.6)** … Backend + Prometheus + Grafana + 各 exporter

## いちばん速い始め方

各マシンで1回ずつ実行するだけです。

```bash
# GPU PC で
cd ~/Project/shopai-dashboard && ./setup.sh gpu-pc

# Backend VM で(GPU PC から rsync 後)
cd ~/shopai-dashboard && ./setup.sh backend-vm
```

`setup.sh` は前提チェック → 秘密値の自動生成 → ネットワーク自動検出 → 起動 →
自動検証まで行い、root が要る所は実行すべきコマンドを表示します。
詳細な手順とトラブルシュートは **`SETUP.md`** を見てください。

## どこに何があるか

| 場所 | 中身 |
| --- | --- |
| `setup.sh` / `SETUP.md` | セットアップ自動化と手順書(まずここ) |
| `README.md` | 構成・段階導入・受け入れ条件 |
| `backend/` | FastAPI に組み込む `/metrics` 計装(`README-integration.md`) |
| `gpu-exporter/` | GPU PC 常駐の nvidia-smi exporter |
| `monitoring/` | Prometheus 設定・アラート・Grafana provisioning・4ダッシュボード JSON |
| `sql/` | Grafana 用 read-only DB ユーザ |
| `scripts/` | `verify_*.sh`(各段の検証)、`build_dashboards.py`(JSON 生成) |

## 困ったら

- 検証: `scripts/verify_vllm_metrics.sh` / `verify_gpu_metrics.sh` /
  `verify_backend_metrics.sh` / `verify_prometheus_targets.sh`
- よくある詰まり: `SETUP.md` のトラブルシュート表
- ダッシュボードを直したい: `scripts/build_dashboards.py` を編集 → 再生成 → JSON をコミット

## 約束ごと

- Grafana / Prometheus は **LAN / VPN 内のみ**。インターネット非公開。
- Prometheus の label に質問本文・回答本文・session_id 等の**高カーディナリティ/個人情報を入れない**。
- Grafana の DB ユーザは **SELECT のみ**(`sql/grafana_readonly_user.sql`)。
- 秘密値は `.env`(gitignore 済み)。`.env.example` を雛形に。
