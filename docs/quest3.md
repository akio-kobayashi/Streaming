# Quest 3 Client Setup

Quest 3 側は、まず `client/quest-web` として同一リポジトリ内のサブプロジェクトで管理する。
ASR サーバー、CLI、通常 Web クライアントと WebSocket プロトコルを共有しつつ、Quest 3 固有の表示、入力、実機検証メモはこの文書に集約する。

Quest Browser は初期検証用の入口として使う。
最終的な常用クライアントとして採用するかは、パススルー字幕表示、マイク権限、長時間安定性、起動導線を実機で確認してから決める。

## 目的

- Quest 3 のパススルー映像を維持したまま、画面下部に放送字幕風の字幕を表示する。
- Quest 3 を音声入力端末兼字幕表示端末として使う。
- Whisper/VAD は GPU 付き ASR サーバーで動かす。
- Quest 3 側は WebSocket API のみを契約として使う。

## 初期サブプロジェクト

```text
client/quest-web/
  README.md             Quest Browser / WebXR client notes
  index.html            future Quest-specific entrypoint
  app.js                future Quest-specific UI logic
  styles.css            future Quest-specific caption layout

docs/
  quest3.md             setup, constraints, validation notes
  protocol.md           WebSocket protocol, when extracted

shared/
  protocol/             message examples and schema fragments
```

初期段階では `client/web` の実装を参照し、Quest 3 固有の画面密度、字幕位置、設定 UI、パススルー検証だけを `client/quest-web` に分ける。

## セットアップ方針

1. PC で ASR サーバーを起動する。
2. PC ブラウザで `client/web` の接続、録音、字幕表示を確認する。
3. Quest 3 Browser で通常の 2D 字幕ページとして接続確認する。
4. Quest 3 用に `client/quest-web` を作り、字幕表示を下部固定、設定 UI を折りたたみにする。
5. WebXR でパススルー映像を維持した字幕オーバーレイを検証する。
6. WebXR で不足する場合だけ、`unity-quest/` を追加してネイティブ化を検討する。

## 起動例

ASR サーバー:

```bash
python3 -m server.app --host 0.0.0.0 --port 8000 --config config.yaml
```

通常 Web クライアント:

```bash
npm run dev
```

Quest 3 用 Web クライアント:

```bash
npm run dev:quest
```

Quest 3 Browser からは、HTTPS 配信された URL を開く。
実機のマイク入力を使う場合は HTTPS/WSS を前提にする。

同一 LAN で接続できない場合や、証明書準備を一時的に簡略化したい場合は、ngrok などの HTTPS/WSS トンネルを使って検証できる。
ただし、音声データが外部サービスを通るため、公開 URL の扱い、認証、検証データの内容には注意する。

## Quest 3 表示仕様

デフォルトは放送字幕風表示とする。

- 表示位置: 画面下部
- 背景色: 半透明黒
- 文字色: 白
- 未確定文字色: 薄い灰色
- 表示行数: 2 行
- 1 行あたりの文字数: 22 文字
- スクロール方式: `push_up`

字幕設定 UI で変更可能にする項目:

- 文字サイズ
- 文字色
- 未確定文字色
- 背景色
- 背景透明度
- 表示行数
- 1 行あたりの文字数

## 検証項目

- Quest 3 Browser で HTTPS ページを開ける。
- マイク権限を取得できる。
- WebSocket / WSS で ASR サーバーへ接続できる。
- Quest 3 の音声が PCM チャンクとして送信される。
- サーバーから `partial` / `final` を受け取れる。
- `stable_text` / `unstable_text` が色分け表示される。
- `push_up` 表示で古い字幕が上に流れる。
- 字幕設定を Quest 3 上で変更できる。
- パススルー映像を維持した字幕表示が可能か確認する。

## WebXR と Unity の判断

当面は Web ベースで進める。
Unity / ネイティブ Quest アプリへ移るのは、以下のいずれかが明確になった場合に限る。

- Quest Browser ではパススルー映像上に十分安定した字幕オーバーレイを出せない。
- WebXR ではパススルー上に期待通り字幕を固定できない。
- Quest Browser のマイク入力や低遅延表示に制約が大きい。
- 配布、権限管理、常用運用でネイティブアプリが必要になる。
- コントローラ、ハンドトラッキング、空間固定 UI を本格的に使う。

## 未確定事項

- Quest 3 Browser 上での WebXR パススルー字幕表示の可否。
- HTTPS/WSS 証明書を Quest 3 が受け入れるための運用方法。
- Quest 3 実機でのマイク音質、サンプルレート、遅延。
- 長時間利用時のバッテリー、発熱、ブラウザ安定性。
