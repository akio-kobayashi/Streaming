# Server and Client Test Procedure

サーバー、CLI クライアント、ブラウザクライアント、Quest 3 クライアントのテスト手順をまとめる。
Whisper/VAD 本体は GPU マシンで後続接続するため、まずはインターフェース、WebSocket、音声チャンク送信、字幕 UI を段階的に確認する。

## テスト段階

1. 静的チェック
2. Python 依存関係のセットアップ
3. サーバー単体テスト
4. CLI クライアント送信テスト
5. Flet クライアント接続テスト
6. ブラウザクライアント送信テスト
7. Quest 3 接続テスト
8. GPU サーバー接続後の ASR 統合テスト

## 1. 静的チェック

依存関係をインストールしなくても、構文チェックは実行できる。

```bash
cd Streaming
python3 -m py_compile server/app.py server/config.py server/schemas.py server/session.py client/cli/send_wav.py
node --check client/web/app.js
node -e "JSON.parse(require('fs').readFileSync('package.json', 'utf8')); console.log('package ok')"
```

期待結果:

- Python の構文エラーが出ない。
- `node --check` が成功する。
- `package ok` が表示される。

## 2. Python 環境セットアップ

サーバーと CLI クライアントを同じ Python 仮想環境で動かす。

```bash
cd Streaming
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

確認:

```bash
python -c "import fastapi, uvicorn, websockets, yaml; print('deps ok')"
```

期待結果:

```text
deps ok
```

## 3. サーバー単体テスト

ASR サーバーを起動する。

```bash
source .venv/bin/activate
python -m server.app --host 127.0.0.1 --port 8000 --config config.yaml
```

別ターミナルで health check を行う。

```bash
curl http://127.0.0.1:8000/health
```

期待結果:

```json
{"status":"ok"}
```

注意:

- 現段階では Whisper/VAD は未接続なので、音声認識結果はまだ返らない。
- WebSocket で受信した音声チャンクに対して `audio_received` を返すところまで確認する。

WebSocket の最小疎通だけを確認する場合は、Node.js の組み込み WebSocket を使った smoke test を使える。

```bash
npm run test:ws -- ws://127.0.0.1:8000/ws ja
```

外部 WSS で確認する場合:

```bash
npm run test:ws -- wss://<public-host>/ws ja
```

期待結果:

- `ready` が返る。
- `config` が返る。
- 3 個の無音 PCM チャンクに対して `audio_received` が返る。
- `stopped` が返る。

## 4. CLI クライアント送信テスト

16 kHz / mono / 16-bit PCM WAV を用意する。
初期 CLI はリサンプリングを行わないため、条件に合わない WAV は事前に変換する。

入力 WAV の条件:

- mono
- PCM 16-bit
- 推奨 sample rate: 16000 Hz

送信:

```bash
source .venv/bin/activate
python -m client.cli.send_wav \
  --server ws://127.0.0.1:8000/ws \
  --file sample.wav \
  --language ja \
  --chunk-ms 50
```

期待結果:

- サーバーから `ready` が返る。
- `start` 後に `config` が返る。
- チャンク送信ごとに `audio_received` が返る。
- 最後に `stopped` が返る。

例:

```json
{"type":"audio_received","session_id":"s-...","chunks_received":1,"bytes_received":1600,"audio_ms_received":50}
```

## 5. Flet クライアント接続テスト

Flet クライアントは PC 向け通常クライアント候補として使う。
初期実装では、GUI から WSS に接続し、無音 PCM チャンクを送って `audio_received` を確認する。

セットアップ:

```bash
python3 -m venv .venv-flet
source .venv-flet/bin/activate
pip install -r requirements-flet.txt
```

起動:

```bash
python -m client.flet.app
```

デスクトップアプリを npm から起動:

```bash
npm run dev:flet
```

補助的に Web 表示で起動:

```bash
python -m client.flet.app --web --host 127.0.0.1 --port 8550
```

Web 表示を npm から起動:

```bash
npm run dev:flet:web
```

確認手順:

1. WebSocket URL に `wss://<public-host>/ws` を入れる。
2. 言語を選ぶ。
3. `Smoke test` を押す。
4. Event log に `ready`, `config`, `audio_received`, `stopped` が出ることを確認する。
5. 字幕表示欄に `audio_received` が表示されることを確認する。

期待結果:

- GUI から WSS 接続できる。
- サーバーに PCM チャンクを送れる。
- `audio_received` と `stopped` を受け取れる。

## 6. ブラウザクライアント送信テスト

通常ブラウザクライアントを起動する。

```bash
npm run dev
```

ブラウザで開く。

```text
http://127.0.0.1:5173
```

確認手順:

1. WebSocket URL が `ws://127.0.0.1:8000/ws` になっていることを確認する。
2. `Connect` を押す。
3. `Record` を押してマイク権限を許可する。
4. 発話する。
5. イベントログに `audio_received` が増えることを確認する。
6. 字幕設定の背景色、文字色、文字サイズ、行数、1 行文字数を変更する。

期待結果:

- WebSocket が接続される。
- マイク入力がサーバーへ送信される。
- サーバーから `audio_received` が返る。
- 字幕オーバーレイの設定変更が画面に反映される。

注意:

- `http://127.0.0.1` はブラウザ上でマイク許可される場合がある。
- 別計算機や Quest 3 からマイク入力する場合は HTTPS/WSS を使う。

## 7. Quest 3 接続テスト

Quest 3 では HTTPS/WSS を前提にする。
初期検証では通常 Web クライアント、次に Quest 3 用サブプロジェクトを使う。

Quest 3 用静的クライアント:

```bash
npm run dev:quest
```

実機検証手順:

1. ASR サーバーを `--host 0.0.0.0` で起動する。
2. ブラウザクライアントまたは Quest 3 クライアントを HTTPS で配信する。
3. Quest 3 とサーバー計算機を同一 LAN に接続する。
4. Quest 3 Browser でクライアント URL を開く。
5. マイク権限を許可する。
6. WSS のサーバー URL を指定する。
7. `Connect` / `Record` を実行する。
8. サーバーに `audio_received` が届くことを確認する。
9. 字幕オーバーレイの下部表示、行数、色、文字サイズを確認する。
10. パススルー映像を維持した字幕表示が可能か記録する。

確認すべき項目:

- マイク権限が取れるか。
- Quest 3 Browser から WSS 接続できるか。
- 音声チャンク送信が途切れないか。
- 字幕 UI が視野下部で読めるか。
- 設定 UI が邪魔にならないか。
- パススルー表示と字幕表示を両立できるか。

### ngrok 等のトンネルを使う場合

同一 LAN で接続できない場合や、Quest 3 用に一時的な HTTPS/WSS URL が必要な場合は、ngrok などのトンネルサービスを使える。

基本方針:

- サーバーはローカルで `127.0.0.1:8000` または `0.0.0.0:8000` に起動する。
- トンネルサービスで `https://...` の公開 URL を作る。
- WebSocket 接続先は `wss://<public-host>/ws` にする。
- ブラウザクライアントも必要に応じて HTTPS で公開する。

確認手順:

1. ASR サーバーを起動する。
2. トンネルを起動し、公開 HTTPS URL を取得する。
3. Quest 3 Browser で HTTPS のクライアントページを開く。
4. WebSocket URL に `wss://<public-host>/ws` を指定する。
5. `Connect` / `Record` を実行する。
6. `audio_received` が返ることを確認する。

注意:

- トンネル経由では遅延が増える可能性がある。
- 音声データが外部トンネルを通るため、研究データや個人情報を扱う場合は慎重に使う。
- 公開 URL を第三者に共有しない。
- 長時間運用や本番用途では、認証付きのリバースプロキシや VPN を検討する。

## 8. GPU サーバー接続後の ASR 統合テスト

GPU 付きマシンで Whisper/VAD を接続したあとに行う。

確認項目:

- `utterance_start` が発話開始時に返る。
- `partial` が逐次返る。
- `stable_text` と `unstable_text` が分かれて返る。
- 無音後に `final` が返る。
- `utterance_end` が返る。
- 言語切替が次発話から反映される。
- 字幕が `push_up` で更新される。

期待メッセージ例:

```json
{
  "type": "partial",
  "session_id": "s-123",
  "utterance_id": "u-001",
  "language": "ja",
  "text": "今日は天気が",
  "stable_text": "今日は",
  "unstable_text": "天気が"
}
```

## トラブルシュート

`ModuleNotFoundError: No module named 'fastapi'`

- `.venv` を有効化しているか確認する。
- `pip install -r requirements.txt` を実行する。

ブラウザでマイクが使えない

- `localhost` または HTTPS で開いているか確認する。
- Quest 3 実機では HTTPS を使う。
- ブラウザのマイク権限を確認する。

WebSocket が接続できない

- サーバーを `--host 0.0.0.0` で起動しているか確認する。
- ファイアウォールがポートを塞いでいないか確認する。
- HTTP ページから WSS、HTTPS ページから WS のような mixed content になっていないか確認する。

CLI で WAV が送れない

- WAV が mono / 16-bit PCM か確認する。
- 初期 CLI はリサンプリングしないため、必要なら事前変換する。

Quest 3 で字幕が読みにくい

- `caption.font_size_px` を大きくする。
- `caption.line_count` を 2 から 3 に増やす。
- `caption.background_opacity` を上げる。
- `caption.chars_per_line` を小さくする。
