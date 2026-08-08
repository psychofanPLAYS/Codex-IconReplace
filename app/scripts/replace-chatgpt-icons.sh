#!/usr/bin/env bash
set -euo pipefail

# Script directory (scripts/) and parent repo directory
SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
REPO_DIR="$(cd -P "$SCRIPT_DIR/.." && pwd)"

# Set working directory to REPO_DIR anchor point
cd "$REPO_DIR"

echo "Anchor point (REPO_DIR): $REPO_DIR"

# Resolve application paths with fallback support for $HOME/Applications
if [[ -d "/Applications/ChatGPT.app" ]]; then
  SOURCE_APP="/Applications/ChatGPT.app"
  RENAMED_APP="/Applications/Codex.app"
elif [[ -d "$HOME/Applications/ChatGPT.app" ]]; then
  SOURCE_APP="$HOME/Applications/ChatGPT.app"
  RENAMED_APP="$HOME/Applications/Codex.app"
elif [[ -d "/Applications/Codex.app" ]]; then
  SOURCE_APP="/Applications/ChatGPT.app"
  RENAMED_APP="/Applications/Codex.app"
elif [[ -d "$HOME/Applications/Codex.app" ]]; then
  SOURCE_APP="$HOME/Applications/ChatGPT.app"
  RENAMED_APP="$HOME/Applications/Codex.app"
else
  SOURCE_APP="/Applications/ChatGPT.app"
  RENAMED_APP="/Applications/Codex.app"
fi

ASSETS_DIR="$REPO_DIR/assets"
BACKUP_ROOT="$REPO_DIR/_backups"

# 1. HARDENED GUARD CHECK: Exit immediately BEFORE creating any folder or backup if already done
if [[ -d "$RENAMED_APP" ]]; then
  echo "============================================================"
  echo "[WARNING] Operation has already been completed!"
  echo "'$RENAMED_APP' already exists."
  echo "No changes or backup folders were created."
  echo "============================================================"
  exit 0
fi

# 2. Check if ChatGPT.app exists
if [[ ! -d "$SOURCE_APP" ]]; then
  echo "[ERROR] Source application not found: $SOURCE_APP" >&2
  echo "Make sure ChatGPT.app is installed in /Applications or $HOME/Applications." >&2
  exit 1
fi

RESOURCE_DIR="$SOURCE_APP/Contents/Resources"
if [[ ! -d "$RESOURCE_DIR" ]]; then
  echo "[ERROR] Resources folder not found: $RESOURCE_DIR" >&2
  exit 1
fi

if [[ ! -d "$ASSETS_DIR" ]]; then
  echo "[ERROR] Assets folder not found: $ASSETS_DIR" >&2
  exit 1
fi

icon_files=(
  "icon-codex-light.png"
  "icon-chatgpt.png"
  "icon-codex-dark-color.png"
  "icon-chatgpt.icns"
  "electron.icns"
  "app.icns"
)

# 3. Create timestamped backup ONLY AFTER guard checks pass
TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "Backing up existing icons to: $BACKUP_DIR"
for file in "${icon_files[@]}"; do
  dst="$RESOURCE_DIR/$file"
  if [[ -f "$dst" ]]; then
    cp "$dst" "$BACKUP_DIR/"
    echo "  Backed up: $file"
  fi
done

# 4. Copy replacement icons from assets/ into app bundle
echo "Replacing icons in app bundle..."
copy_count=0
for file in "${icon_files[@]}"; do
  src="$ASSETS_DIR/$file"
  dst="$RESOURCE_DIR/$file"

  if [[ ! -f "$src" ]]; then
    echo "[ERROR] Missing source icon: $src" >&2
    exit 1
  fi

  cp "$src" "$dst"
  ((copy_count+=1))
  echo "  Updated: $file"
done

# 5. Rename ChatGPT.app to Codex.app & update Info.plist
echo "Renaming $SOURCE_APP to $RENAMED_APP..."
mv "$SOURCE_APP" "$RENAMED_APP"

INFO_PLIST="$RENAMED_APP/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
  echo "Updating Info.plist display name to 'Codex'..."
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'Codex'" "$INFO_PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Codex'" "$INFO_PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleName string 'Codex'" "$INFO_PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :CFBundleName 'Codex'" "$INFO_PLIST" 2>/dev/null || true
fi

# 6. Re-sign app bundle to prevent Gatekeeper error warnings
echo "Re-signing app bundle..."
xattr -cr "$RENAMED_APP" 2>/dev/null || true
codesign --force --sign - "$RENAMED_APP" >/dev/null 2>&1 || true

# 7. Set Finder custom preview icon (Cmd+I preview icon)
PREVIEW_ICON="$ASSETS_DIR/app.icns"
if [[ -f "$PREVIEW_ICON" ]]; then
  echo "Setting custom Finder (Cmd+I) preview icon..."
  swift -e 'import AppKit; if let img = NSImage(contentsOfFile: "'"$PREVIEW_ICON"'") { _ = NSWorkspace.shared.setIcon(img, forFile: "'"$RENAMED_APP"'", options: []) }' 2>/dev/null || true
fi

# 8. FINAL STEP: Refresh Finder & Dock icon cache + launch Codex for 2s to force Dock update
echo "Refreshing Finder & Dock icon caches..."
touch "$RENAMED_APP"
touch "$RENAMED_APP/Contents/Resources"
qlmanage -r >/dev/null 2>&1 || true
qlmanage -r cache >/dev/null 2>&1 || true
killall Finder >/dev/null 2>&1 || true
killall Dock >/dev/null 2>&1 || true
# Gentle touch refresh instead of aggressive process termination
echo "Refreshing Codex.app bundle timestamps..."
touch "$RENAMED_APP"
touch "$RENAMED_APP/Contents/Resources"

echo "============================================================"
echo "Successfully replaced icons and renamed app to Codex.app!"
echo "Icons updated: $copy_count"
echo "Backup saved in: $BACKUP_DIR"
echo "============================================================"
