# Flet Client

Flet クライアントは実験扱いに降格する。
PC 向け通常クライアントの主開発は `client/qt` に移す。

降格理由:

- リアルタイムスペクトログラムの描画品質がブラウザ版に届かない。
- マイク入力、UI 更新、配布ランタイムの制御が複雑になりすぎる。
- 放送字幕風のステージ表示と進行表示を安定して作りにくい。
- デスクトップクライアントとしての完成度を上げるほど Flet 側の制約に引きずられる。

## 管理方針

```text
client/
  qt/         primary PC desktop client
  flet/       experimental prototype
```

Flet クライアントはサーバー内部には依存しない。
`shared/protocol` の WebSocket メッセージ仕様だけを契約とする。

今後はバグ修正や比較検証に限って維持し、新機能は原則として Qt 版に実装する。
