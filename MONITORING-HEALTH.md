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

### 4) 他端末から UI を見る (LAN / VPN)

Grafana・Prometheus・Alertmanager は `0.0.0.0` で待ち受けているので、ネットワーク
到達性とホストのファイアウォールさえ許可すれば、どの端末のブラウザからでも見られる。

**(a) 同一LANの他PC・タブレットから** — 監視機の UFW で UI ポートを LAN に開放:

```bash
# 監視機で (LAN を 192.168.0.0/24 と仮定。自分の LAN に合わせる)
! sudo ufw allow from 192.168.0.0/24 to any port 3000 proto tcp   # Grafana
! sudo ufw allow from 192.168.0.0/24 to any port 9090 proto tcp   # Prometheus
! sudo ufw allow from 192.168.0.0/24 to any port 9093 proto tcp   # Alertmanager
# → 他端末のブラウザで  http://<監視機の LAN IP>:3000
```

**(b) 外出先・別ネットワークから (VPN: Tailscale)** — インターネット非公開のまま、
どの端末からでもアクセス可:

```bash
# 監視機で
! curl -fsSL https://tailscale.com/install.sh | sh
! sudo tailscale up          # 表示URLでブラウザ認証
! sudo ufw allow in on tailscale0   # tailnet からの全ポートを許可
# 見る側の端末 (スマホ/PC) にも Tailscale を入れて同じアカウントでログイン
# → http://<監視機の 100.x.x.x>:3000  (tailscale ip -4 で確認)
```

> セキュリティ方針 (README §22) どおり、Grafana/Prometheus はインターネットに直接
> 公開しない。LAN または VPN(Tailscale/WireGuard) 内に限定する。

### 5) どのPCでも起動できる (可搬性)

このスタックは**どのマシンでも `docker compose -f docker-compose.health.yml up -d`
だけで起動**する（DB 認証情報も不要）。監視対象は `prometheus.health.yml` 冒頭の
LAN IP で指定しているだけなので、監視機をどこに移しても同じ設定で動く。別PCに移す:

```bash
rsync -a ~/Project/shopai-dashboard/ <新監視機>:~/shopai-dashboard/
# 新監視機で .env を用意 (GRAFANA_ADMIN_PASSWORD)・必要なら backend_sd.json
docker compose -f docker-compose.health.yml --env-file .env up -d
```

> 監視機を GPU PC 以外に移すと、本書冒頭の「GPU-PC firewall 注意」(コンテナ→自ホスト
> 遮断) は不要になる（vLLM/GPU が別ホスト＝リモート扱いになるため）。

### 6) タブレット等の端末も監視する

`monitoring/prometheus/devices.json`（gitignore 済み）に IP を足すと、ICMP ping で
死活監視し、Service Health の「📱 端末 死活」に UP/DOWN と応答時間が出る:

```bash
cp monitoring/prometheus/devices.json.example monitoring/prometheus/devices.json
$EDITOR monitoring/prometheus/devices.json   # 店舗端末の IP と name を記入
docker compose -f docker-compose.health.yml restart prometheus
```

> ⚠️ Android タブレットは省電力で WiFi がスリープすると ping が落ち、実際は生きて
> いても DOWN に見えることがある。誤検知が多い場合は WiFi のスリープ無効化、または
> この端末監視を外す。空配列のままなら端末監視は無効（誤検知なし）。

## ダッシュボード「Service Health」の見方

| セクション | 内容 |
| --- | --- |
| 全体ステータス | `全死活チェック`(1つでも赤→要対応) / ダウン中の数 / 発火中アラート |
| サービス別 死活 | 各ホスト ping・各ポート TCP・/health の UP/DOWN グリッド |
| ホスト リソース | CPU / メモリ / ディスク使用率 (ホスト別) |
| 稼働時間 / 応答時間 | 稼働時間(再起動で 0 に戻る) / 外形応答時間 |
| コンテナ稼働 | ホスト別コンテナ数 / コンテナ CPU 上位 |
| 📱 端末 死活 | `devices.json` の端末の UP/DOWN・ping 応答時間（IP 登録時のみ表示） |

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
