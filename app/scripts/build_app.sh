#!/usr/bin/env bash
# ==============================================================================
# Build Script for IconReplace.app
#
# Generates a standalone native macOS application bundle (IconReplace.app) in dist/
# containing embedded Python source code, launcher binary, Info.plist, and AppIcon.icns.
# ==============================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
APP_DIR="$( cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "${APP_DIR}/.." >/dev/null 2>&1 && pwd )"
APP_BUNDLE="${PROJECT_ROOT}/IconReplace.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
SRC_DEST_DIR="${RESOURCES_DIR}/src"

echo "=== Building IconReplace.app ==="
echo "Project Root: ${PROJECT_ROOT}"
echo "App Source Dir: ${APP_DIR}"
echo "App Bundle Target: ${APP_BUNDLE}"

# 1. Clean previous build directory
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}"
mkdir -p "${RESOURCES_DIR}"
mkdir -p "${SRC_DEST_DIR}"

# 2. Copy python source files
echo "Copying source modules..."
cp -R "${APP_DIR}/src/"*.py "${SRC_DEST_DIR}/"

# 3. Generate AppIcon.icns from system icon if needed
SYS_ICON="/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns"
if [ -f "${SYS_ICON}" ]; then
    cp "${SYS_ICON}" "${RESOURCES_DIR}/AppIcon.icns"
fi

# 4. Create launcher executable script in Contents/MacOS/IconReplace
cat << 'EOF' > "${MACOS_DIR}/IconReplace"
#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
RESOURCES_DIR="${SCRIPT_DIR}/../Resources"
MAIN_SCRIPT="${RESOURCES_DIR}/src/main.py"

# Locate system python3 executable
PYTHON_EXEC="$(which python3)"
if [ -z "${PYTHON_EXEC}" ] || [ ! -x "${PYTHON_EXEC}" ]; then
    PYTHON_EXEC="/usr/bin/python3"
fi

exec "${PYTHON_EXEC}" "${MAIN_SCRIPT}" "$@"
EOF

chmod +x "${MACOS_DIR}/IconReplace"

# 5. Create Info.plist bundle metadata
cat << 'EOF' > "${CONTENTS_DIR}/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>IconReplace</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.antigravity.iconreplace</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>IconReplace</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# 6. Sanitize extended attributes & sign bundle with ad-hoc signature
echo "Signing application bundle..."
xattr -cr "${APP_BUNDLE}" 2>/dev/null || true
codesign --force --sign - "${APP_BUNDLE}" 2>/dev/null || true

echo "=== Build Complete ==="
echo "Application bundle created successfully at:"
echo "  ${APP_BUNDLE}"
