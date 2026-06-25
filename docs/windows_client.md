# Windows Desktop Client

Windows ユーザー向けには、Flet クライアントをダブルクリックで起動できるようにする。
初期配布では `.bat` ランチャーを使い、必要に応じて後続で `.exe` 化する。

## 方式

### 方式 A: BAT ランチャー

`run_flet_client.bat` をダブルクリックして起動する。

特徴:

- 初回起動時に `.venv-flet` を作る。
- 初回起動時に `requirements-flet.txt` をインストールする。
- 2 回目以降はそのまま Flet デスクトップアプリを起動する。
- Python 3 がインストールされている必要がある。
- `python` コマンドが見つからない場合は `py -3` にフォールバックする。
- WSL の `\\wsl.localhost\...` 配下から実行された場合でも、一時ドライブに割り当てて起動する。

起動:

```text
run_flet_client.bat
```

サーバー URL を指定する場合は、コマンドプロンプトから以下を実行する。

```bat
run_flet_client.bat --server-url wss://<public-host>/ws
```

### 方式 B: EXE 化

Python を入れていない利用者向けには `.exe` 配布を検討する。
まずは PyInstaller で検証する。
ビルド時には `assets/app-icon.ico` を生成し、アプリのアイコンとしてバンドルする。

```bat
scripts\windows\build_flet_exe.bat
```

成功すると以下に出力される。

```text
dist\StreamingASRClient\StreamingASRClient.exe
```

## 推奨する段階

1. 開発者・研究室内: `run_flet_client.bat`
2. 外部テスター: PyInstaller 版 `.exe`
3. 継続運用: 署名付きインストーラまたは更新機構付き配布

## 注意点

- 初回の `.bat` 起動では依存関係のダウンロードが必要になる。
- Python 3 を Windows に入れる場合は、インストーラで `Add python.exe to PATH` を有効にする。
- ネットワーク制限のある Windows 環境では、事前に `.venv-flet` を作成した配布パッケージを用意する。
- `.exe` 化した場合でも、WebSocket 接続先や証明書、ファイアウォール設定は別途確認する。
- マイク入力を追加した後は、Windows のマイク権限も確認する。
- アイコンの元データは `assets/app-icon.svg`、Windows 用 `.ico` は `scripts/windows/create_icon.py` で生成する。
- PyInstaller で生成した `.exe` は未署名のため、Windows SmartScreen の警告が出る可能性がある。
