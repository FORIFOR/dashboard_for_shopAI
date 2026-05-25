# セットアップ手順(だれでも実行可)

このダッシュボードは **2台のマシン**にまたがって動きます。各マシンで `./setup.sh`
を1回ずつ実行するだけで構築できます。root が要る箇所はスクリプトが**実行すべき
コマンドを表示**するので、それだけ `sudo`(Claude Code なら `! sudo ...`)で実行します。

| マシン | 役割 | IP | 実行コマンド |
| --- | --- | --- | --- |
| GPU PC | vLLM + GPU exporter | 192.168.0.15 | `./setup.sh gpu-pc` |
| Backend VM | Prometheus + Grafana + 各 exporter | 192.168.0.6 | `./setup.sh backend-vm` |

役割を省略すると `nvidia-smi` の有無で自動判定し、確認を求めます。

---

## 事前に必要なもの

- **GPU PC**: `nvidia-smi`, `python3`, `curl`(vLLM が :8000 で稼働中であること)
- **Backend VM**: `docker` + `docker compose`, `python3`, `curl`
  - ShopAI backend に `/metrics` の結線が済んでいること(本リポジトリ `backend/README-integration.md`)
  - PostgreSQL に `question_logs` / `staff_calls` 等の業務テーブルがあること

`setup.sh` は不足している前提を最初にチェックして停止します。

---

## 手順

### A. GPU PC(192.168.0.15)

```bash
cd ~/Project/shopai-dashboard
./setup.sh gpu-pc
```

スクリプトがやること:
1. 前提チェック(nvidia-smi / python3 / curl)
2. venv 作成 + `prometheus-client` 導入
3. vLLM `/metrics`(:8000)を検証
4. GPU exporter を 5 秒テスト起動して :9401 を検証
5. **常駐化コマンドを表示** → 自分で1回実行:
   ```
   ! sudo bash ~/Project/shopai-dashboard/gpu-exporter/install_systemd_service.sh
   ```
6. ファイアウォールがあれば(表示される通り):
   ```
   ! sudo ufw allow from 192.168.0.6 to any port 9401 proto tcp
   ```

### B. Backend VM(192.168.0.6)

```bash
# GPU PC から転送(初回のみ)
rsync -a ~/Project/shopai-dashboard/ saiteku@192.168.0.6:~/shopai-dashboard/

ssh saiteku@192.168.0.6
cd ~/shopai-dashboard
./setup.sh backend-vm
```

スクリプトがやること:
1. 前提チェック(docker / compose / python3 / curl。docker が sudo 必須なら自動で sudo 使用)
2. `.env` が無ければ作成し、**Grafana 管理パスワードと dashboard 用 DB パスワードを自動生成**
   → 表示に従い `POSTGRES_PASSWORD` だけ既存DBのものに編集
3. backend の docker ネットワークを自動検出して `.env` に記録
   (見つからなければ `SHOPAI_NETWORK=<名前> ./setup.sh backend-vm` で指定)
4. **read-only DB ユーザ作成コマンドを表示** → 初回1回だけ実行:
   ```
   psql "postgresql://shopai@localhost:5432/shopai" \
     -v pw="'<.env の SHOPAI_DASHBOARD_DB_PASSWORD>'" \
     -f sql/grafana_readonly_user.sql
   ```
5. compose 構成を検証 → スタックを起動
6. 12 秒待って Prometheus のターゲットを検証
7. Grafana / Prometheus の URL を表示

完了後:
- **Grafana**: `http://192.168.0.6:3000`(`admin` / `.env` の `GRAFANA_ADMIN_PASSWORD`)
- **Prometheus targets**: `http://192.168.0.6:9090/targets`(全部 UP が目標)
- 左メニュー → Dashboards → **ShopAI** フォルダに4画面が自動表示

---

## うまくいったかの確認

| 確認 | コマンド / 場所 | 期待 |
| --- | --- | --- |
| vLLM | `scripts/verify_vllm_metrics.sh 192.168.0.15:8000` | PASS 10/10 |
| GPU | `scripts/verify_gpu_metrics.sh 192.168.0.15:9401` | PASS |
| Backend | `scripts/verify_backend_metrics.sh 192.168.0.6:8080` | PASS |
| Prometheus | `scripts/verify_prometheus_targets.sh 192.168.0.6:9090` | 全 UP |
| Grafana | ブラウザ | 4画面表示・値が入る |

`/chat` を数回叩くと route/latency/LLM/RAG の各パネルに値が入り始めます。

---

## トラブルシュート

| 症状 | 原因 / 対処 |
| --- | --- |
| Prometheus で `shopai-backend` が DOWN | backend に `/metrics` 結線が未反映、または `api` コンテナ名/ネットワーク不一致。`SHOPAI_NETWORK` を確認 |
| `shopai-vllm` / `shopai-gpu` が DOWN | GPU PC 側の :8000 / :9401 に Backend VM から到達不可。ファイアウォール(ufw allow)を確認 |
| `postgres` が DOWN | `.env` の `POSTGRES_PASSWORD` 不一致、または DB サービス名が `db` でない(compose と datasource を実名に変更) |
| Grafana の PostgreSQL パネルがエラー | read-only ユーザ未作成、またはテーブル/列名が実スキーマと不一致。`scripts/build_dashboards.py` の SQL を直して再生成 |
| ネットワーク自動検出に失敗 | `docker network ls` で名前を調べ `SHOPAI_NETWORK=<名前> ./setup.sh backend-vm` |
| docker が permission denied | `setup.sh` は自動で sudo を使う。ユーザを docker グループに入れれば sudo 不要に |

> セキュリティ: Grafana / Prometheus は **LAN または VPN 内のみ**。インターネットに直接公開しないこと。
