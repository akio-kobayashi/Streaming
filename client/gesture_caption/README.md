# Gesture Caption Client

OpenCV のカメラ映像上で手のジェスチャーにより字幕フレームを移動、リサイズし、サーバー側 Whisper 系 ASR 結果を表示する macOS 向けプロトタイプ。

FLUX.2 は使用しない。クライアント側は MediaPipe、OpenCV、sounddevice、WebSocket に限定し、音声認識は ASR サーバーで行う。
既存の ASR のみのクライアントである `client/cli`、`client/web`、`client/flet` は残し、このクライアントは追加の実験用 UI として分離する。

## Setup

推奨は macOS 用スクリプトから起動する方法。
repo 外から実行しても `Streaming` 直下へ移動し、専用仮想環境 `.venv-gesture` を作成して不足依存関係を入れる。

```bash
scripts/macos/run_gesture_caption.sh --gesture-only
```

手動でセットアップする場合は、必ず repo 直下で実行する。

```bash
python3 -m venv .venv-gesture
source .venv-gesture/bin/activate
python -m pip install --upgrade pip
python -m pip install -r client/gesture_caption/requirements.txt
```

## Run

まずカメラ、ジェスチャー、字幕フレームだけを確認する。
このモードではマイク入力も ASR サーバー接続も行わない。

```bash
python -m client.gesture_caption.main --gesture-only
```

`/Users/akio/Documents/GitHub` など repo の一つ上から直接 `python3 -m client.gesture_caption.main` を実行すると、`client` パッケージを見つけられない。
その場合は `cd Streaming` してから実行するか、上記の `scripts/macos/run_gesture_caption.sh` を使う。

macOS で `Failed to open camera` または `not authorized to capture video` が出る場合は、
「システム設定 > プライバシーとセキュリティ > カメラ」で、このコマンドを実行している Terminal / iTerm / Codex にカメラ権限を付与する。
権限付与後にまだ開けない場合は `--camera 1` など別のカメラ番号を試す。

ASR サーバーへ音声を送信する。

```bash
python -m client.gesture_caption.main \
  --server-url ws://127.0.0.1:8000/ws \
  --language ja \
  --latency-ms 1000
```

MediaPipe Tasks の Hand Landmarker モデルを使う場合は、`hand_landmarker.task` を取得してパスを指定する。
`scripts/macos/run_gesture_caption.sh` は `client/gesture_caption/models/hand_landmarker.task` が無い場合に自動取得する。
指定しない場合は、まず `mediapipe.solutions.hands` を試し、それが無い MediaPipe では上記のローカルモデルを使う。

```bash
python -m client.gesture_caption.main \
  --hand-landmarker-model path/to/hand_landmarker.task \
  --gesture-only
```

## Gestures

- 片手ピンチ: 字幕フレームの位置変更
- ピンチ解除: 位置固定
- 両手ピンチ: 字幕フレームのサイズ変更

字幕表示・非表示はジェスチャーではなく音声コマンドで行う。
`字幕表示` / `字幕出して` で表示し、`字幕消して` / `字幕オフ` で非表示にする。

各ジェスチャーは状態機械と連続フレーム判定を通して確定する。

## Voice Commands

ASR 結果が「字幕」「フレーム」「枠」を含む場合だけ、字幕操作コマンドとして解釈する。
コマンドとして解釈された発話は字幕本文には追加しない。

初期コマンド:

- `字幕表示`, `字幕出して`: フレーム表示
- `字幕消して`, `字幕オフ`: フレーム非表示
- `字幕クリア`, `字幕リセット`: 字幕履歴を消去
- `字幕文字大きく`, `字幕フォント大きく`: 文字を大きくする
- `字幕文字小さく`, `字幕フォント小さく`: 文字を小さくする
- `字幕上へ`, `字幕下へ`, `字幕左へ`, `字幕右へ`: フレーム移動
- `字幕広げて`, `字幕狭く`: フレーム幅変更
- `字幕高く`, `字幕低く`: フレーム高さ変更

## Files

- `main.py`: カメラ、MediaPipe、WebSocket ASR、描画のメインループ
- `gesture.py`: ランドマークからジェスチャーイベントを生成
- `caption_frame.py`: 字幕フレームの状態管理と OpenCV 描画
- `audio_stream.py`: マイク入力と PCM チャンク送信キュー
- `server_asr_client.py`: ASR サーバーへの WebSocket 接続
- `voice_command.py`: ASR テキストから字幕操作コマンドを抽出
- `config.py`: 初期設定値

## Notes

- Whisper / VAD / partial / final 生成はサーバー側で行う。
- クライアントは 16kHz mono PCM を WebSocket で送信し、`partial` / `final` を受け取る。
- 映像処理と WebSocket ASR は別スレッドに分ける。
- まずは安定動作を優先し、精密なジェスチャー分類や字幕遅延最適化は後段で扱う。
