# 死活監視スタック (Service Health / Uptime)

「Backend PC が落ちていないか」「各サーバ・サービスが動いているか」を**一画面**で
見て、異常時は**通知**する、軽量で独立した監視スタック。深掘り系ダッシュボード
(RAG品質/LLM内部) とは別物で、**どのPCでも creds なしで起動できる**（PostgreSQL 不要）。

## 設計の要点

1. **監視は監視対象の上で動かさない。** Prometheus/Grafana を Backend VM の上で
   動かすと、Backend VM が落ちたとき監視ごと止まって「落ちたこと」が見えない。
   → このスタックは **3台目の常時稼働機**（小型NUC / Raspberry Pi / 予備機）で動かす。
2. **外形監視 (blackbox)** で ping / TCP / HTTP を外側から叩き、メトリクスを出さない
   サービスも「生きているか」を判定する。
3. **通知 (Alertmanager)** で、画面を見ていなくてもダウンに気づける。

## 構成

```
        ┌─────────────── 3台目: 常時稼働機 (どのPCでも可) ───────────────┐
        │  docker-compose.health.yml                                    │
        │   Prometheus  ─ blackbox(ping/tcp/http) ─┐                     │
        │   Grafana (:3000) ← Service Health 画面   │  scrape by LAN IP  │
        │   Alertmanager (:9093) → Slack/Discord/Mail                    │
        └───────────────────────────┬───────────────┬───────────────────┘
                                     │               │
            docker-compose.agent.yml │               │ docker-compose.agent.yml
        ┌─────────────────┐          ▼               ▼          ┌─────────────────┐
        │ Backend VM .6   │  node-exporter:9100  cadvisor:8081  │ GPU PC .15      │
        │ FastAPI :8080   │  vLLM :8000  GPU exporter :9401      │                 │
        │ PostgreSQL :5432│                                      │                 │
        └─────────────────┘                                      └─────────────────┘
```

監視するホスト/ポートは `monitoring/prometheus/prometheus.health.yml` の冒頭で
IP を直接編集する（ホストが増減・移動したらここを直す）。

## セットアップ

### 1) 監視される側 — Backend VM (.6) と GPU PC (.15) 各々で

```bash
rsync -a ~/Project/shopai-dashboard/ <host>:~/shopai-dashboard/   # まだ無ければ転送
cd ~/shopai-dashboard
docker compose -f docker-compose.agent.yml up -d        # node-exporter + cadvisor
# ファイアウォールがある場合のみ、監視機からの到達を許可:
# sudo ufw allow from <監視機IP> to any port 9100 proto tcp
# sudo ufw allow from <監視機IP> to any port 8081 proto tcp
```

> Backend VM で既に `docker-compose.monitoring.yml` を動かしている場合、node-exporter /
> cadvisor は重複するので agent は不要（監視を3台目へ移すなら monitoring 側を停止）。

### 2) 監視する側 — 3台目の常時稼働機で

```bash
cd ~/shopai-dashboard
cp .env.example .env
$EDITOR .env                       # GRAFANA_ADMIN_PASSWORD だけ設定すれば起動する
docker compose -f docker-compose.health.yml --env-file .env up -d
```

- ダッシュボード: `http://<監視機>:3000` (admin / 設定したパスワード) → 起動時に
  **Service Health** 画面が開く。
- Prometheus: `http://<監視機>:9090/targets` で全ターゲット UP を確認。
- Alertmanager: `http://<監視機>:9093`。

### 3) 通知の設定 (任意だが推奨)

初期状態は通知 OFF（receiver が空）で安全に起動する。`monitoring/alertmanager/alertmanager.yml`
の `receivers:` で Slack / Discord / Email / Webhook のいずれか1つを記入して有効化し、

```bash
docker compose -f docker-compose.health.yml restart alertmanager
```

動作確認は、監視対象のどれか1つ（例: agent の node-exporter）を止めると
`ServicePortDown` / `HostUnreachable` が発火する。

### 4) 他PC・外出先から見る (VPN)

同一LANの他PCからは `http://<監視機>:3000` でそのまま閲覧可。外出先からも見たい
場合は **Tailscale** が簡単（インターネットに公開せず、どこからでもアクセス可）。

```bash
# 監視機で:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# → 表示された 100.x.x.x で http://100.x.x.x:3000 にどの端末からでもアクセス
```

> セキュリティ方針 (README §22) どおり、Grafana/Prometheus はインターネットに直接
> 公開しない。LAN または VPN(Tailscale/WireGuard) 内に限定する。

## ダッシュボード「Service Health」の見方

| セクション | 内容 |
| --- | --- |
| 全体ステータス | `全死活チェック`(1つでも赤→要対応) / ダウン中の数 / 発火中アラート |
| サービス別 死活 | 各ホスト ping・各ポート TCP・/health の UP/DOWN グリッド |
| ホスト リソース | CPU / メモリ / ディスク使用率 (ホスト別) |
| 稼働時間 / 応答時間 | 稼働時間(再起動で 0 に戻る) / 外形応答時間 |
| コンテナ稼働 | ホスト別コンテナ数 / コンテナ CPU 上位 |

ダッシュボードは `python3 scripts/build_dashboards.py` で再生成して JSON をコミット。

## アラート一覧 (`monitoring/prometheus/alerts-health.yml`)

| アラート | 条件 | 深刻度 |
| --- | --- | --- |
| HostUnreachable | ping 1分応答なし | critical |
| ServicePortDown | TCP ポート閉塞 1分 | critical |
| HTTPHealthFailing | /health が 2xx でない 2分 | warning |
| NodeExporterDown | ホストメトリクス取得不可 2分 | warning |
| HostRebooted | 起動時刻が10分以内に変化 | warning |
| DiskAlmostFull | ディスク90%超 10分 | warning |
| MemoryHigh | メモリ92%超 10分 | warning |
| GPUTemperatureHigh | GPU 85℃超 5分 | warning |
