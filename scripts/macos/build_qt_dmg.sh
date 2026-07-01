#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="${APP_NAME:-StreamingASRQt}"
VERSION="${VERSION:-0.1.0}"
APP_PATH="${APP_PATH:-dist/$APP_NAME.app}"
DMG_NAME="${DMG_NAME:-$APP_NAME-$VERSION-mac}"
DMG_PATH="${DMG_PATH:-dist/$DMG_NAME.dmg}"
STAGING_DIR="${STAGING_DIR:-dist/dmg-$APP_NAME}"
VOLUME_NAME="${VOLUME_NAME:-$APP_NAME}"
BUILD_APP="${BUILD_APP:-1}"

if [ "$BUILD_APP" = "1" ]; then
  scripts/macos/build_qt_app.sh
fi

if [ ! -d "$APP_PATH" ]; then
  echo "App bundle not found: $APP_PATH" >&2
  echo "Run scripts/macos/build_qt_app.sh first, or set APP_PATH." >&2
  exit 1
fi

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

echo "Staging $APP_PATH..."
cp -R "$APP_PATH" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

mkdir -p "$(dirname "$DMG_PATH")"
rm -f "$DMG_PATH"

echo "Creating $DMG_PATH..."
hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Built $DMG_PATH"
