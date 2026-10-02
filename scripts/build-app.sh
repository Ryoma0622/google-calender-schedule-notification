#!/usr/bin/env bash
# Builds build/CalBar.app. With "install", also replaces /Applications/CalBar.app and launches it.
set -euo pipefail
cd "$(dirname "$0")/.."

swift build -c release --product CalBar
bin_dir="$(swift build -c release --show-bin-path)"
app="build/CalBar.app"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$bin_dir/CalBar" "$app/Contents/MacOS/CalBar"
cp Resources/Info.plist "$app/Contents/Info.plist"

iconset="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" Resources/AppIcon.png --out "$iconset/icon_${size}x${size}.png" >/dev/null
  sips -z "$((size * 2))" "$((size * 2))" Resources/AppIcon.png --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$app/Contents/Resources/AppIcon.icns"

# Ad-hoc signature: enough for EventKit and notifications on this Mac.
codesign --force --sign - "$app"
echo "Built $app"

if [[ "${1:-}" == "install" ]]; then
  osascript -e 'tell application id "com.calbar.app" to quit' 2>/dev/null || true
  pkill -f "/Applications/CalBar.app/Contents/MacOS/CalBar" 2>/dev/null || true
  sleep 1
  rm -rf /Applications/CalBar.app
  cp -R "$app" /Applications/CalBar.app
  open /Applications/CalBar.app
  echo "Installed /Applications/CalBar.app"
fi
