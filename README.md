# Streaming Multilingual ASR

Whisper を用いたストリーミング多言語音声認識システムの設計メモ。
クライアントから短い音声チャンクを送信し、サーバー側で逐次認識を行い、調整可能な遅延で途中結果と確定結果を返す。

## 目的

- クライアントが指定したターゲット言語の音声を低遅延で逐次テキスト化する。
- Whisper ベースの認識器をサーバー側で常駐させ、複数クライアントから利用できるようにする。
- 遅延と認識精度のバランスを設定で調整できるようにする。
- VAD により発話区間と無音区間を検出し、文末または発話末で認識結果を確定する。

## 想定ユースケース

- ブラウザまたはローカルアプリからマイク入力を送信する。
- サーバーは途中認識をリアルタイムに返し、発話末で確定テキストを返す。
- クライアントは `partial` と `final` を区別して表示する。

## クライアント種別

入力側クライアントは、最終的にはブラウザを主対象にする。
ブラウザであればインストール不要で使え、WebSocket と Web Audio API によりマイク入力を直接送信できる。

ただし、開発初期には CLI クライアントも作る。
CLI クライアントは WAV ファイルやローカルマイク入力を決まった条件で送信できるため、サーバー、VAD、Whisper 推論、遅延制御の検証に向いている。

ネイティブアプリは後段の選択肢とする。
常駐録音、低レベル音声制御、OS 連携、配布済み端末での利用が必要になった場合に追加する。

初期方針:

- Primary client: browser client
- Development client: Python CLI client
- Optional future client: native desktop/mobile app

## ブラウザクライアント構成

ブラウザクライアントは、音声送信だけでなく、発話単位の状態を見ながら操作できる UI とする。

主な UI 要素:

- 発話ごとのスペクトログラム表示
- スクロール型テキストペイン
- 出力言語の選択
- 接続、録音、停止の操作
- VAD 状態と認識状態の簡易表示

### スペクトログラム

スペクトログラムは現在の発話を対象に表示する。
発話開始で表示バッファをリセットし、発話中の音声だけを横方向に追加していく。
発話終了後は、次の発話開始まで最後のスペクトログラムを保持する。

発話開始の判定は、初期実装ではサーバー側 VAD の `utterance_start` イベントを使う。
クライアント側 VAD を有効にする場合は、クライアント側で先に表示を開始し、サーバー側イベントで補正する。

表示の候補:

- Web Audio API の `AnalyserNode` による簡易スペクトログラム
- AudioWorklet で取得した PCM から STFT を計算する詳細スペクトログラム

MVP では `AnalyserNode` による軽量表示で十分とする。

### テキストペイン

認識結果はスクロール型のテキストペインに表示する。
`partial` は現在行として更新し、`final` を受け取ったら確定行として履歴に追加する。

表示ルール:

- `partial`: 現在発話の暫定テキストとして上書き表示する。
- `final`: 確定テキストとして履歴に追加する。
- `stable_text`: 確定に近い部分として通常色で表示する。
- `unstable_text`: まだ変化し得る部分として薄い色または背景色付きで表示する。
- 発話ごとに `language`, `start_ms`, `end_ms` を内部的に保持する。
- 表示は自動スクロールを基本にし、ユーザーが過去ログを読んでいる間は追従を一時停止できるようにする。

### 差分表示

NHK のリアルタイム字幕のように、ストリーミング中の認識結果を差分表示する。
サーバーは連続する Whisper 出力を比較し、変化しにくい前方部分を `stable_text`、変化しやすい末尾部分を `unstable_text` として返す。
ブラウザは `stable_text` を通常色、`unstable_text` を薄い色や下線付きで表示する。

表示例:

```text
今日は天気が [いいかもしれ]
```

この例では `今日は天気が ` が安定部分、`いいかもしれ` が未確定部分になる。
次の認識で末尾が変わった場合、未確定部分だけを差し替える。

初期実装では、前回テキストと今回テキストの最長共通接頭辞を使って安定部分を推定する。
ただし、単純な接頭辞だけでは短い修正に弱いため、次の段階で文字単位または文節単位の diff に拡張する。

差分表示の責務:

- サーバー: 安定化ポリシーを持ち、`stable_text` と `unstable_text` を計算する。
- クライアント: 受信した文字列を色分け表示する。
- `final` 受信時: 全文を確定色にし、未確定表示を解除する。

### 出力言語選択

ブラウザ UI には出力言語の選択欄を置く。
選択した言語は、次の発話から適用することを基本とする。
これにより、発話中に言語を切り替えた場合でも、途中結果の言語が混在しにくい。

発話中に言語が変更された場合の初期方針:

- 現在発話中なら、サーバーへ `config` で `language_apply: "next_utterance"` として通知する。
- サーバーは現在発話を `final` にしたあと、新しい `language` を適用する。
- 無音中なら、即座に次発話用の `language` として反映する。

クライアント側では、現在適用中の言語と、次発話から適用予定の言語を区別して表示できるようにする。

## Quest 3 連携計画

Quest 3 連携は、まず Meta Quest Browser でブラウザクライアントを動かす方針にする。
既存の WebSocket / Web Audio API ベースの設計をそのまま使えるため、専用アプリを作る前に音声入力、ストリーミング認識、差分字幕表示を検証できる。

### 初期接続方式

```text
Quest 3 Browser
  - microphone permission
  - Web Audio API capture
  - PCM chunk sender
  - spectrogram and captions UI
  - language selector

LAN / Wi-Fi
  - HTTPS page delivery
  - WSS or secure WebSocket transport

ASR Server
  - FastAPI WebSocket
  - VAD
  - Whisper inference
```

Quest 3 側はブラウザで Web クライアントを開き、マイク入力を取得してサーバーへ PCM チャンクを送る。
サーバーは通常のブラウザクライアントと同じ WebSocket API で受ける。

### 接続条件

- Quest 3 と ASR サーバーは同一 LAN または到達可能なネットワーク上に置く。
- ブラウザのマイク入力を使うため、ページ配信は HTTPS を基本にする。
- WebSocket も本番または実機検証では WSS を基本にする。
- 開発時はローカル証明書またはリバースプロキシで HTTPS/WSS を用意する。
- サーバー側 GPU マシンを使う場合、Quest 3 は軽量な入出力端末として扱う。

### Quest 3 用 UI

Quest 3 では視野内で読める字幕 UI が重要になる。
通常ブラウザ表示の段階では、2D ページとして以下を表示する。

- 中央または下部に大きめのストリーミング字幕
- `stable_text` と `unstable_text` の色分け
- 発話ごとのスペクトログラム
- 出力言語の選択
- 接続状態、マイク状態、VAD 状態

### 放送字幕風オーバーレイ

Quest 3 では、通常のスクロール型テキストペインとは別に、放送字幕のような字幕オーバーレイを主表示として用意する。
ブラウザクライアント上で CSS と UI 設定を使えば、背景色、文字色、表示行数、1 行あたりの文字数、文字サイズなどを制御できる。

字幕オーバーレイの主な設定:

- `caption_position`: `bottom`, `center`, `top`
- `caption_background_color`: 字幕背景色
- `caption_background_opacity`: 字幕背景の透明度
- `caption_text_color`: 確定部分の文字色
- `caption_unstable_text_color`: 未確定部分の文字色
- `caption_font_size`: 文字サイズ
- `caption_line_count`: 表示行数
- `caption_chars_per_line`: 1 行あたりの目安文字数
- `caption_padding`: 字幕領域の余白
- `caption_text_align`: `left`, `center`
- `caption_scroll_mode`: `push_up`

表示は `stable_text` と `unstable_text` を分けて行う。
`stable_text` は通常の字幕色、`unstable_text` は薄い色や別背景で表示し、`final` になった時点で全体を確定色に戻す。

1 行あたりの文字数は、CSS の `max-width` と JavaScript 側の折り返し処理を組み合わせて制御する。
日本語は空白区切りがないため、MVP では文字数ベースで折り返し、後段で句読点や文節を考慮した折り返しに拡張する。

### 字幕スクロール

放送字幕として、字幕枠の表示行数には上限を設ける。
新しい字幕は下側に表示し、確定した字幕が追加されるたびに既存行を上へ送る。
表示行数を超えた古い字幕は上から消す。

表示モデル:

- 字幕枠は `caption_line_count` 行の固定高さにする。
- `partial` は最下行の現在発話として更新する。
- `final` を受信したら、現在発話を確定字幕行として字幕キューに追加する。
- キューが `caption_line_count` を超えたら、古い行を上から削除する。
- 次の `partial` は再び最下行に表示し、確定行を必要に応じて上へ押し上げる。

表示例:

```text
行1: それでは次のニュースです。
行2: 現在、東京では雨が
```

ここで `行2` が未確定の `partial` で、`final` になると確定行として残る。
次の発話が入ると、古い行は上へ移動し、表示行数を超えたものから消える。

Quest 3 用の初期表示設定:

```yaml
caption:
  position: bottom
  background_color: "#000000"
  background_opacity: 0.75
  text_color: "#ffffff"
  unstable_text_color: "#d0d0d0"
  font_size_px: 36
  line_count: 2
  chars_per_line: 22
  scroll_mode: push_up
  text_align: center
```

設定 UI は字幕の近くに常時出すのではなく、通常は折りたたみパネルにする。
Quest 3 上では表示領域を邪魔しないよう、設定変更時だけ開く形にする。

WebXR 対応は第 2 段階とする。
WebXR を使う場合は、字幕パネルを空間内に固定表示し、コントローラまたはハンドトラッキングで言語選択や録音開始を行う。

### 実装段階

1. PC ブラウザで Web クライアントを完成させる。
2. HTTPS/WSS でローカルネットワークからアクセスできるようにする。
3. Quest 3 Browser でマイク権限、音声取得、WebSocket 接続を確認する。
4. Quest 3 の表示密度に合わせて字幕 UI と操作 UI を調整する。
5. 必要に応じて WebXR 字幕パネルを追加する。
6. さらに OS 連携や配布が必要になった場合のみ、Unity またはネイティブアプリ化を検討する。

## 全体構成

```text
Client
  - microphone capture
  - optional client-side VAD
  - chunk encoder
  - WebSocket transport
  - utterance spectrogram
  - language selector
  - partial/final display

WebSocket Server
  - session manager
  - audio buffer
  - optional server-side VAD
  - streaming policy
  - Whisper inference worker
  - result stabilizer

Whisper Backend
  - faster-whisper or openai-whisper
  - multilingual transcription
  - GPU/CPU selectable runtime
```

## 推奨する初期構成

MVP では、VAD はサーバー側を基本にする。
理由は、クライアント実装を薄く保てること、Web/CLI/録音ファイルなど入力元が変わっても同じ文末判定を使えること、実験時に VAD パラメータをサーバーだけで変更できること。

ただし、将来的にはクライアント側 VAD も選択可能にする。
クライアント側 VAD はネットワーク送信量を減らせるが、端末差やブラウザ差が出やすいため、最初から唯一の判定源にはしない。

## 通信方式

音声チャンクの送受信には WebSocket を使う。
HTTP の逐次 POST よりセッション状態を扱いやすく、サーバーから `partial` を随時 push できる。

### クライアントからサーバー

制御メッセージは JSON、音声チャンクは binary frame とする。

```json
{
  "type": "start",
  "sample_rate": 16000,
  "channels": 1,
  "format": "pcm_s16le",
  "language": "ja",
  "task": "transcribe",
  "latency_ms": 800,
  "vad_mode": "server"
}
```

```json
{
  "type": "config",
  "latency_ms": 1200,
  "vad_silence_ms": 700,
  "min_utterance_ms": 300,
  "language": "en",
  "language_apply": "next_utterance"
}
```

```json
{
  "type": "stop"
}
```

音声 binary frame は 16 kHz, mono, PCM 16-bit を標準とする。
ブラウザ側で別形式になる場合は、クライアントまたはサーバーで 16 kHz mono に変換する。

### サーバーからクライアント

```json
{
  "type": "utterance_start",
  "session_id": "s-123",
  "utterance_id": "u-001",
  "language": "ja",
  "start_ms": 0
}
```

```json
{
  "type": "partial",
  "session_id": "s-123",
  "utterance_id": "u-001",
  "revision": 12,
  "language": "ja",
  "text": "今日は天気が",
  "stable_text": "今日は",
  "unstable_text": "天気が",
  "start_ms": 0,
  "end_ms": 1800,
  "stable": false
}
```

```json
{
  "type": "final",
  "session_id": "s-123",
  "utterance_id": "u-001",
  "revision": 15,
  "language": "ja",
  "text": "今日は天気がいいですね。",
  "stable_text": "今日は天気がいいですね。",
  "unstable_text": "",
  "start_ms": 0,
  "end_ms": 2600,
  "reason": "vad_silence"
}
```

```json
{
  "type": "utterance_end",
  "session_id": "s-123",
  "utterance_id": "u-001",
  "language": "ja",
  "end_ms": 2600,
  "reason": "vad_silence"
}
```

```json
{
  "type": "error",
  "message": "unsupported sample rate"
}
```

## ターゲット言語

クライアントは WebSocket 接続開始時の `start` メッセージでターゲット言語を指定する。
サーバーはそのセッション中、指定された `language` を Whisper の認識条件として使い、同じ言語の認識結果を `partial` / `final` として返す。

`language` は Whisper が扱う ISO 639-1 系の言語コードを基本とする。
例: `ja`, `en`, `zh`, `ko`, `fr`, `de`, `es`。

初期方針では `task: "transcribe"` を使い、音声の言語のまま文字起こしする。
翻訳を行う場合は、別途 `task: "translate"` を許可するが、これは英訳用途として明示的に扱い、通常の多言語 ASR とは分ける。

言語指定の扱い:

- `language` が指定された場合: その言語として認識する。
- `language` が `auto` の場合: Whisper の言語判定に任せる。
- 認識結果には `language` を含め、クライアント側で表示・ログ・評価に使えるようにする。
- セッション途中で言語を変更する場合は、原則として現在の発話を `final` にしてから新しい言語設定に切り替える。
- 発話ごとに `utterance_id` を付与し、スペクトログラム、途中結果、確定結果、言語設定を対応付ける。

## 音声処理パイプライン

1. クライアントがマイク音声を 20-100 ms 程度のチャンクで取得する。
2. 音声を 16 kHz, mono, PCM 16-bit に整える。
3. WebSocket でサーバーへ送る。
4. サーバーはセッションごとにリングバッファへ追加する。
5. VAD が発話中か無音かを判定する。
6. 一定間隔で Whisper に直近の音声窓を渡して認識する。
7. 前回結果と比較し、安定した部分を `partial` として返す。
8. 無音が一定時間続いたら発話末として `final` を返し、確定済みバッファを整理する。

## ストリーミング認識方針

Whisper 自体は完全な逐次認識モデルではないため、短い音声窓を重ねながら再デコードする方式を採る。

- `chunk_ms`: クライアント送信単位。初期値 50 ms。
- `decode_interval_ms`: サーバーが認識を走らせる間隔。初期値 500 ms。
- `latency_ms`: 出力を安定させるために待つ目標遅延。初期値 800-1200 ms。
- `window_ms`: Whisper に渡す音声窓。初期値 10-20 s。
- `overlap_ms`: 前回窓との重なり。初期値 1-2 s。

`latency_ms` を小さくすると反応は速いが修正が増える。
大きくすると表示は安定するが遅くなる。

## 結果安定化

Whisper の再デコードでは、直近の末尾文字列が変化しやすい。
そのため、以下のように扱う。

- `partial`: 変更される可能性がある途中結果。
- `stable partial`: 複数回のデコードで共通して出た前方部分。
- `final`: VAD または明示的な stop により確定した結果。

初期実装では、前回テキストと今回テキストの最長共通接頭辞を安定部分の候補とする。
精度が足りない場合は、単語または文節単位の差分に拡張する。

`partial` では、表示用に `stable_text` と `unstable_text` を返す。
`text` は両者を結合した全文であり、クライアントが単純表示だけを行う場合に使える。
`final` では `stable_text` に全文を入れ、`unstable_text` は空にする。

## VAD 設計

### サーバー側 VAD

候補:

- Silero VAD: 精度が高く、Python サーバーに組み込みやすい。
- WebRTC VAD: 軽量で低遅延だが、音声条件によって調整が必要。

初期実装では Silero VAD を優先する。

主なパラメータ:

- `vad_threshold`: 発話判定のしきい値。
- `min_speech_ms`: 発話として扱う最小長。
- `min_silence_ms`: 発話末とみなす無音長。
- `speech_pad_ms`: 発話前後に付与する余白。

### クライアント側 VAD

将来的なオプションとして、ブラウザで音量ベースまたは WebRTC VAD 相当の処理を入れる。
クライアント側 VAD を使う場合でも、サーバー側で簡易的な再判定を行い、誤った切断を補正できるようにする。

## 文末判定

文末は単純な句点だけでなく、VAD とテキストの状態を組み合わせて判定する。

初期実装:

- `min_silence_ms` 以上の無音で発話末とする。
- 発話末のタイミングで最後の認識結果を `final` にする。
- 句点、疑問符、感嘆符が出た場合でも、短すぎる無音では確定しない。

拡張案:

- 日本語句読点や終助詞を見て文末らしさを推定する。
- Whisper の segment timestamp を利用する。
- LLM または軽量分類器で文末判定を補助する。

## サーバー内部モジュール

```text
server/
  app.py                WebSocket entrypoint
  config.py             runtime settings
  session.py            client session state
  audio_buffer.py       ring buffer and resampling boundary
  vad.py                VAD interface and implementations
  whisper_worker.py     model loading and inference
  stabilizer.py         partial/final text stabilization
  schemas.py            message schemas

client/
  web/                  browser microphone client
  cli/                  wav/microphone test client

tests/
  test_stabilizer.py
  test_vad_policy.py
  test_message_schema.py

requirements.txt        server and CLI Python dependencies
pyproject.toml          optional Python project metadata
package.json            browser client dependencies and scripts
config.yaml             default runtime configuration
README.md               design, setup, and operation guide
```

## 実装候補技術

- Server: Python, FastAPI, WebSocket
- ASR: faster-whisper
- VAD: Silero VAD
- Audio: numpy, soundfile, optionally ffmpeg
- Client Web: TypeScript, Web Audio API
- Client CLI: Python, sounddevice

MVP では Python サーバーと Python CLI クライアントを先に作る。
その後、ブラウザクライアントを追加する。

## インストール方針

サーバーとクライアントは、他の計算機にも展開できるように手順化する。
README には、サーバー用、CLI クライアント用、ブラウザクライアント用、Quest 3 接続用の手順を分けて記載する。

配布の基本方針:

- ソースコードは Git で取得できるようにする。
- Python 依存関係は `requirements.txt` または `pyproject.toml` に固定する。
- ブラウザクライアント依存関係は `package.json` に固定する。
- サーバー設定は `config.yaml` で変更できるようにする。
- GPU あり/なしで Whisper の `device`, `compute_type`, `model` を切り替えられるようにする。
- Quest 3 接続用に HTTPS/WSS の起動例を用意する。

### サーバー計算機

サーバー計算機は Whisper と VAD を実行する。
GPU が使える場合はサーバー側で GPU を使い、Quest 3 やブラウザクライアントは軽量な入出力端末として使う。

想定手順:

```bash
git clone <repository-url> Streaming
cd Streaming
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python -m server.app --host 0.0.0.0 --port 8000 --config config.yaml
```

GPU サーバーでは、環境に合わせて PyTorch / CUDA / faster-whisper のインストール手順を別途確認する。
CPU 実行では `whisper.model` を `tiny`, `base`, `small` など軽めにし、`decode_interval_ms` を長めにする。

### CLI クライアント計算機

CLI クライアントは、WAV ファイル送信やローカルマイク入力による検証に使う。
サーバーと同じ計算機でも、別の計算機でも実行できる。

想定手順:

```bash
git clone <repository-url> Streaming
cd Streaming
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m client.cli.send_wav --server ws://<server-host>:8000/ws --file sample.wav --language ja
```

CLI クライアントが別計算機にある場合は、`<server-host>` にサーバー計算機の IP アドレスまたはホスト名を指定する。

### ブラウザクライアント計算機

ブラウザクライアントは PC ブラウザ、タブレット、Quest 3 Browser で利用する。
開発時は Vite などの開発サーバー、本番または Quest 3 検証では HTTPS 配信を使う。

想定手順:

```bash
git clone <repository-url> Streaming
cd Streaming
npm install
npm run dev -- --host 0.0.0.0
```

ブラウザから `http://<client-host>:5173` を開き、WebSocket 接続先として `ws://<server-host>:8000/ws` を指定する。
マイク入力を使う実機検証では HTTPS が必要になるため、`https://<client-host>` と `wss://<server-host>/ws` で接続できる構成を用意する。

### Quest 3 接続

Quest 3 は Meta Quest Browser からブラウザクライアントへアクセスする。

想定手順:

1. サーバー計算機で ASR サーバーを起動する。
2. ブラウザクライアントを HTTPS で配信する。
3. Quest 3 とサーバー/クライアント計算機を同一 LAN に接続する。
4. Quest 3 Browser で `https://<client-host>` を開く。
5. マイク権限を許可する。
6. 接続先として `wss://<server-host>/ws` を指定する。
7. 発話し、字幕オーバーレイと `partial` / `final` の表示を確認する。

### ネットワーク設定

別計算機から利用する場合は、以下を確認する。

- サーバーが `0.0.0.0` で listen していること。
- ファイアウォールで WebSocket ポートを許可していること。
- ブラウザクライアントからサーバーのホスト名または IP アドレスを解決できること。
- HTTPS/WSS を使う場合、証明書をブラウザまたは Quest 3 が受け入れられること。
- 同一 LAN 検証では、PC と Quest 3 が同じ Wi-Fi セグメントにあること。

### インストール成果物

実装時には、最低限以下を用意する。

- `requirements.txt`: Python サーバー/CLI の依存関係
- `package.json`: Web クライアントの依存関係と起動スクリプト
- `config.example.yaml`: 編集用の設定例
- `.env.example`: 必要な環境変数の例
- `README.md`: インストール、起動、Quest 3 接続手順
- `scripts/`: HTTPS/WSS 起動や証明書準備を補助するスクリプト

## MVP マイルストーン

1. FastAPI WebSocket サーバーを作る。
2. Whisper モデルをサーバー起動時にロードする。
3. WAV ファイルをチャンク送信する CLI クライアントを作る。
4. 固定間隔で再デコードし、`partial` を返す。
5. Silero VAD を入れ、無音で `final` を返す。
6. `latency_ms` と VAD パラメータを WebSocket の `start/config` で変更可能にする。
7. `requirements.txt`, `package.json`, `config.example.yaml` を用意する。
8. ブラウザマイククライアントを追加する。
9. HTTPS/WSS 経由で Quest 3 Browser から接続検証する。
10. ログと簡単な評価スクリプトを追加する。

## 初期設定値

```yaml
audio:
  sample_rate: 16000
  channels: 1
  format: pcm_s16le

streaming:
  chunk_ms: 50
  decode_interval_ms: 500
  latency_ms: 1000
  window_ms: 15000
  overlap_ms: 1500

vad:
  mode: server
  backend: silero
  threshold: 0.5
  min_speech_ms: 250
  min_silence_ms: 700
  speech_pad_ms: 200

whisper:
  backend: faster-whisper
  model: small
  language: ja
  device: auto
  compute_type: auto

caption:
  position: bottom
  background_color: "#000000"
  background_opacity: 0.75
  text_color: "#ffffff"
  unstable_text_color: "#d0d0d0"
  font_size_px: 36
  line_count: 2
  chars_per_line: 22
  scroll_mode: push_up
  text_align: center
```

## 注意点

- Whisper は末尾の認識が揺れやすいため、`partial` は常に修正され得るものとして扱う。
- 日本語では空白区切りがないため、単語単位の安定化よりも文字列または文節単位の安定化が扱いやすい。
- 低遅延化しすぎると誤認識の修正頻度が上がる。
- VAD の発話末判定が早すぎると文が分割され、遅すぎると `final` が遅れる。
- GPU がない環境ではモデルサイズと `decode_interval_ms` を保守的にする。

## 実装可能性レビュー

README の設計は実装可能である。
ただし、Whisper は本来ストリーミング専用モデルではないため、短い音声窓を重ねて再デコードする擬似ストリーミングとして実装する。
この前提を置けば、サーバー、CLI クライアント、ブラウザクライアント、Quest 3 表示はいずれも段階的に実装できる。

実装しやすい部分:

- FastAPI WebSocket による双方向通信
- PCM チャンク受信とセッション別リングバッファ
- faster-whisper による多言語認識
- Silero VAD による発話開始/終了判定
- `partial` / `final` / `utterance_start` / `utterance_end` のイベント化
- `stable_text` / `unstable_text` による差分字幕表示
- ブラウザ上の字幕オーバーレイ、色、行数、文字サイズ、押し上げ表示

実装前に注意する部分:

- ブラウザのマイク入力は Float32 で得られるため、16 kHz mono PCM 16-bit への変換処理が必要になる。
- 音声 binary frame は raw PCM を基本にし、必要なら `seq`, `client_time_ms`, `sample_count` などのメタデータを別 JSON で送る。
- Whisper 推論は重いため、WebSocket 受信ループをブロックせず、推論ワーカーまたは非同期キューに分離する。
- Quest 3 Browser のマイク権限と AudioWorklet / Web Audio API の挙動は実機で早めに確認する。
- Quest 3 からマイクを使うには HTTPS/WSS 構成を早めに用意する。
- 字幕の 1 行文字数は CSS だけでは安定しにくいため、JavaScript 側の文字数ベース折り返しを入れる。

MVP で後回しにできる部分:

- WebXR 空間字幕パネル
- クライアント側 VAD
- 文節単位の高度な diff
- LLM による文末判定
- ネイティブアプリ化

最初の実装は、CLI クライアントでサーバーの認識・VAD・差分出力を固め、その後ブラウザ UI と Quest 3 接続へ進む。

## 次に作るもの

最初の実装では、以下の最小セットを作る。

- `server/app.py`: WebSocket サーバー。実装済み。
- `client/cli/send_wav.py`: WAV をチャンク送信するテストクライアント。実装済み。
- `client/web/`: ブラウザ録音、字幕オーバーレイ、設定 UI の最小版。実装済み。
- `config.example.yaml`: 他計算機へ配布するための設定例。実装済み。
- `requirements.txt`: サーバー/CLI の Python 依存関係。実装済み。
- `package.json`: ブラウザクライアントの起動スクリプト。実装済み。
- `server/whisper_worker.py`: Whisper 推論ラッパー。GPU マシン側で後続実装。
- `server/stabilizer.py`: partial の安定化。Whisper 出力接続時に後続実装。
- `config.yaml`: 実行環境ごとの設定。`config.example.yaml` から作成する。
