# Quest Web Client

Quest 3 Browser / WebXR 向けの字幕クライアントを置くサブプロジェクト。

このディレクトリは、通常ブラウザクライアント `client/web` から Quest 3 固有の UI を分離するために使う。
初期段階では `client/web` の WebSocket 接続、マイク入力、字幕描画ロジックを再利用し、以下を Quest 3 用に調整する。

- パススルー字幕モード
- 画面下部固定の放送字幕風レイアウト
- 設定 UI の折りたたみ
- Quest 3 実機での文字サイズ、行数、文字数調整
- WebXR 検証

## 起動

```bash
npm run dev:quest
```

初期実装前は、このコマンドは `client/quest-web` を静的配信するための入口として使う。
Quest 3 実機でマイクを使う場合は HTTPS/WSS に切り替える。

## 実装順

1. `client/web` の caption overlay を Quest 3 用に移植する。
2. 字幕のみを主表示にし、スペクトログラムとログはデバッグパネルへ移す。
3. `caption.mode = quest_passthrough_caption` を既定値にする。
4. WebXR パススルー表示を検証する。
5. 必要なら Unity / ネイティブアプリに分岐する。
