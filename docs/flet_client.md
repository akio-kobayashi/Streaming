# Flet Client Plan

通常クライアントは Flet を使った別サブプロジェクトとして作る。
ブラウザクライアントはプロトコル検証と Quest Browser / WebXR 検証用に残し、PC 向けの操作しやすいアプリは `client/flet` で管理する。

## 目的

- サーバーへの WebSocket / WSS 接続を GUI で確認する。
- マイク音声を送信する。
- 認識結果を放送字幕風に表示する。
- 字幕表示設定を GUI で変更する。
- PC デスクトップアプリとして単独起動できるようにする。

## 管理方針

```text
client/
  cli/        automated and WAV-based tests
  web/        browser prototype
  quest-web/  Quest Browser / WebXR prototype
  flet/       primary PC client candidate
```

Flet クライアントはサーバー内部には依存しない。
`shared/protocol` の WebSocket メッセージ仕様だけを契約とする。

## テスト順

1. `scripts/ws_smoke_test.js` で WSS 疎通確認。
2. Flet でサーバーに接続する。
3. Flet で PC マイク入力を送信する。
4. `partial` / `final` の字幕表示を確認する。
5. デスクトップアプリとしての起動手順を整える。

## 注意点

- Flet は PC 向け通常クライアントには向くが、Quest 3 パススルー字幕の本命とは分ける。
- Quest 3 は `client/quest-web` または将来の Unity / Unreal クライアントで扱う。
- Web 表示は補助的な検証用とし、通常利用はデスクトップアプリを主対象にする。
- Flet 本番クライアントは `Connect`、`Record`、`Stop` による実マイク送信を基本動作とする。

## デスクトップアプリ起動

Flet クライアントは PC 上のデスクトップアプリとして単独起動する。

```bash
python -m client.flet.app
```

npm 経由:

```bash
npm run dev:flet
```

Windows のダブルクリック起動:

```text
run_flet_client.bat
```

起動後の基本操作:

1. `WebSocket URL` と `Language`、`Latency ms` を設定する。
2. `Connect` でサーバーに接続する。
3. `Record` で PC マイク入力をサーバーへ送る。
4. `Stop` で録音を止め、サーバーへ `stop` を送る。

サーバー URL を指定する場合:

```bash
python -m client.flet.app --server-url wss://<public-host>/ws
```

補助的に Web 表示で検証する場合:

```bash
python -m client.flet.app --web --host 127.0.0.1 --port 8550
```

npm 経由:

```bash
npm run dev:flet:web
```
