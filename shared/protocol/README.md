# Shared Protocol

ASR サーバー、通常 Web クライアント、Quest 3 クライアント、将来の Unity クライアントで共有する WebSocket メッセージ仕様を置く。

初期実装では README 本体に仕様を書いているが、Quest 3 側が大きくなる段階で以下をここに切り出す。

- client `start` message
- client `config` message
- binary PCM frame assumptions
- server `partial` message
- server `final` message
- server `utterance_start` / `utterance_end`
- caption config schema
