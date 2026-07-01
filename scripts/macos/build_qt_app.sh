#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv-qt}"
APP_NAME="${APP_NAME:-StreamingASRQt}"
APP_PATH="dist/$APP_NAME.app"
ICON_PATH="${ICON_PATH:-assets/app-icon.icns}"
APP_RESOURCES="$APP_PATH/Contents/Resources"
APP_MACOS="$APP_PATH/Contents/MacOS"
APP_PAYLOAD="$APP_RESOURCES/$APP_NAME"
APP_LAUNCHER="$APP_MACOS/$APP_NAME"
USE_ICON="${USE_ICON:-0}"
STRIP_XATTR="${STRIP_XATTR:-0}"
CODESIGN_APP="${CODESIGN_APP:-0}"

scripts/macos/setup_qt_client.sh

echo "Installing PyInstaller..."
"$VENV_DIR/bin/python" -m pip --disable-pip-version-check install pyinstaller

declare -a icon_args=()
if [ "$USE_ICON" = "1" ] && [ -f "$ICON_PATH" ]; then
  icon_args=(--icon "$ICON_PATH")
fi

echo "Building PyInstaller payload..."
PYINSTALLER_CONFIG_DIR=.pyinstaller-cache "$VENV_DIR/bin/pyinstaller" \
  --name "$APP_NAME" \
  --noconfirm \
  --clean \
  --onedir \
  ${icon_args[@]+"${icon_args[@]}"} \
  --collect-all certifi \
  --collect-all sounddevice \
  --collect-all websockets \
  --hidden-import PySide6.QtCore \
  --hidden-import PySide6.QtGui \
  --hidden-import PySide6.QtWidgets \
  client/qt/app.py

echo "Wrapping payload in $APP_PATH..."
rm -rf "$APP_PATH"
mkdir -p "$APP_RESOURCES" "$APP_MACOS"
cp -R "dist/$APP_NAME" "$APP_PAYLOAD"

echo "Writing app Info.plist..."
icon_plist_entry=""
if [ "$USE_ICON" = "1" ] && [ -f "$ICON_PATH" ]; then
  icon_plist_entry='  <key>CFBundleIconFile</key>
  <string>app-icon</string>'
fi

cat > "$APP_PATH/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
${icon_plist_entry}
  <key>CFBundleIdentifier</key>
  <string>local.streaming.$APP_NAME</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>0.1.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Streaming ASR Qt Client uses the microphone to stream speech audio to the configured ASR server.</string>
</dict>
</plist>
PLIST

echo "Writing app launcher..."
cat > "$APP_LAUNCHER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$APP_DIR/Resources/StreamingASRQt/StreamingASRQt" "$@"
SH
chmod +x "$APP_LAUNCHER"

if [ "$USE_ICON" = "1" ] && [ -f "$ICON_PATH" ]; then
  echo "Bundling app icon..."
  cp "$ICON_PATH" "$APP_RESOURCES/app-icon.icns"
fi

if [ "$STRIP_XATTR" = "1" ]; then
  echo "Removing extended attributes..."
  xattr -cr "$APP_PATH" 2>/dev/null || true
fi

if [ "$CODESIGN_APP" = "1" ]; then
  echo "Ad-hoc signing app..."
  codesign --force --deep --sign - "$APP_PATH"
  codesign --verify --deep --verbose=2 "$APP_PATH"
fi

echo "Built $APP_PATH"
