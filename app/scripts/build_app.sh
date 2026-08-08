#!/usr/bin/env bash
# ==============================================================================
# Build Script for IconReplace.app
#
# Bundles IconReplace into a true standalone macOS application bundle using PyInstaller.
# Embeds Python interpreter, CustomTkinter, PIL, dependencies, and assets.
# ==============================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
APP_DIR="$( cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "${APP_DIR}/.." >/dev/null 2>&1 && pwd )"
FINAL_APP_BUNDLE="${PROJECT_ROOT}/IconReplace.app"
SPEC_FILE="${PROJECT_ROOT}/IconReplace.spec"

echo "=== Building Standalone IconReplace.app with PyInstaller ==="
echo "Project Root: ${PROJECT_ROOT}"
echo "Spec File:    ${SPEC_FILE}"
echo "Target App:   ${FINAL_APP_BUNDLE}"

# 1. Verify pyinstaller is available or install it
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found in PATH. Installing via pip..."
    python3 -m pip install --quiet pyinstaller
fi

# 2. Clean previous build artifacts and old app bundle
echo "Cleaning previous build artifacts..."
rm -rf "${PROJECT_ROOT}/build"
rm -rf "${PROJECT_ROOT}/dist"
rm -rf "${FINAL_APP_BUNDLE}"

# 3. Run PyInstaller using spec file
echo "Running PyInstaller build..."
cd "${PROJECT_ROOT}"
pyinstaller --noconfirm --clean "${SPEC_FILE}"

# 4. Move generated bundle to project root if output in dist/
if [ -d "${PROJECT_ROOT}/dist/IconReplace.app" ]; then
    echo "Moving dist/IconReplace.app to project root..."
    mv "${PROJECT_ROOT}/dist/IconReplace.app" "${FINAL_APP_BUNDLE}"
fi

# 5. Clean build directories
rm -rf "${PROJECT_ROOT}/dist"
rm -rf "${PROJECT_ROOT}/build"

# 6. Sanitize extended attributes & sign bundle with ad-hoc signature
if [ -d "${FINAL_APP_BUNDLE}" ]; then
    echo "Sanitizing attributes and signing application bundle..."
    xattr -cr "${FINAL_APP_BUNDLE}" 2>/dev/null || true
    codesign --force --deep --sign - "${FINAL_APP_BUNDLE}" 2>/dev/null || true
else
    echo "ERROR: IconReplace.app bundle was not found after build!"
    exit 1
fi

echo "=== Build Complete ==="
echo "Standalone application bundle successfully generated at:"
echo "  ${FINAL_APP_BUNDLE}"
