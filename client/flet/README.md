# Flet Client

Flet を使った通常クライアント用サブプロジェクト。
Quest 3 / WebXR 検証用の `client/web` / `client/quest-web` とは分け、PC から使う字幕表示・設定 UI・接続確認用アプリとして育てる。

## 目的

- サーバーへ WebSocket / WSS で接続する。
- マイク音声を PCM チャンクとして送信する。
- `partial` / `final` / `stable_text` / `unstable_text` を受け取る。
- 放送字幕風の字幕表示を行う。
- 文字サイズ、文字色、背景色、行数、1 行文字数などを設定できるようにする。

## 位置づけ

- `client/cli`: 自動テスト、WAV 送信、疎通確認
- `client/web`: ブラウザ検証、Quest Browser の初期検証
- `client/quest-web`: Quest 3 / WebXR 向け
- `client/flet`: PC 向け通常クライアント、デスクトップアプリ

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

1. WSS 接続確認と `ready` / `config` / `audio_received` の表示。
2. 字幕オーバーレイ設定 UI。
3. `partial` / `final` の字幕表示。
4. マイク入力と PCM 変換。
5. デスクトップアプリとしての起動方法整理。
6. パッケージ化と配布手順。
