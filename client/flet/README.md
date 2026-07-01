# Flet Client

Flet を使った実験用クライアント。
PC 向け通常クライアントの主開発は `client/qt` に移す。
このサブプロジェクトは、過去実装の確認、比較検証、軽微な接続確認用として残す。

## 目的

- サーバーへ WebSocket / WSS で接続する。
- マイク音声を PCM チャンクとして送信する。
- `partial` / `final` / `stable_text` / `unstable_text` を受け取る。
- 放送字幕風の字幕表示を行う。
- 文字サイズ、文字色、背景色、行数、1 行文字数などを設定できるようにする。
- Flet でどこまで実用 UI を再現できるかを比較対象として記録する。

## 位置づけ

- `client/cli`: 自動テスト、WAV 送信、疎通確認
- `client/web`: ブラウザ検証、Quest Browser の初期検証
- `client/quest-web`: Quest 3 / WebXR 向け
- `client/qt`: PC 向け通常クライアント、デスクトップアプリ
- `client/flet`: 実験用デスクトッププロトタイプ

## セットアップ

```bash
python3 -m venv .venv-flet
source .venv-flet/bin/activate
pip install -r requirements-flet.txt
```

## 起動

Windows でダブルクリック起動する場合:

```text
run_flet_client.bat
```

デスクトップアプリとして起動する場合:

```bash
python -m client.flet.app
```

デスクトップアプリを npm から起動する場合:

```bash
npm run dev:flet
```

外部 WSS を使う場合:

```bash
python -m client.flet.app --server-url wss://<public-host>/ws
```

Web 表示で検証する場合:

```bash
python -m client.flet.app --web --host 127.0.0.1 --port 8550
```

Web 表示を npm から起動する場合:

```bash
npm run dev:flet:web
```

起動後に以下を開く。

```text
http://127.0.0.1:8550
```

## 実装順

今後は新機能を原則として `client/qt` 側に実装する。
Flet 側は以下の用途に限定する。

1. 既存挙動の再確認。
2. Qt 版との比較。
3. 接続処理やメッセージ処理の軽微な検証。
