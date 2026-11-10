#!/usr/bin/env bash
# Build FolderExporter.app + DMG locally on an Apple Silicon Mac.
# No GitHub Actions, no Homebrew, no system-wide Python installation.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo 'This builder must be run on an Apple Silicon Mac (M1/M2/M3/M4 or newer).'
  exit 1
fi

SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/FolderExporter-Build.XXXXXXXX")"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/tooling" "$WORK/python"
cp "$SOURCE/workflow10_test.py" "$SOURCE/WORKFLOW_MANUAL.md" "$SOURCE/workflow_test.py" "$SOURCE/app.py" "$SOURCE/export_core.py" "$SOURCE/storyboard.py" "$SOURCE/storyboard_ui.py" "$SOURCE/studio_link.py" "$SOURCE/media_catalog.py" "$SOURCE/media_catalog_test.py" "$SOURCE/studio_link_test.py" "$SOURCE/integration_test.py" "$SOURCE/selftest.py" "$SOURCE/gui_test.py" "$SOURCE/folder.png" "$SOURCE/FolderExporter.icns" "$WORK/"
cd "$WORK"

printf '\n=== FolderExporter for Apple Silicon ===\n'
printf 'FolderExporter Classic v1.10.0: all compilation occurs on this Mac.\nNothing is uploaded to GitHub.\n'
printf 'Downloading a temporary isolated Python toolchain and required packages...\n\n'

curl -fLsS --retry 3 'https://astral.sh/uv/install.sh' -o install-uv.sh
UV_INSTALL_DIR="$WORK/tooling" UV_NO_MODIFY_PATH=1 sh install-uv.sh
export UV_PYTHON_INSTALL_DIR="$WORK/python"
export UV_PYTHON_BIN_DIR="$WORK/python-bin"
export UV_CACHE_DIR="$WORK/cache"
"$WORK/tooling/uv" python install 3.11
"$WORK/tooling/uv" venv --python 3.11 "$WORK/venv"
"$WORK/tooling/uv" pip install --python "$WORK/venv/bin/python" \
  'psd-tools[composite]==1.26.0' 'clipparse==0.2.0' 'Pillow==12.3.0' 'pyinstaller>=6.10,<7'

printf '\nRunning export safety tests and checking application imports...\n'
# Never launch a temporary GUI during compilation: older builders flashed
# a window on the user's desktop, making it seem like the app had crashed.
"$WORK/venv/bin/python" selftest.py
"$WORK/venv/bin/python" integration_test.py
"$WORK/venv/bin/python" media_catalog_test.py
"$WORK/venv/bin/python" studio_link_test.py
"$WORK/venv/bin/python" workflow_test.py
"$WORK/venv/bin/python" workflow10_test.py
"$WORK/venv/bin/python" -m py_compile app.py export_core.py storyboard.py storyboard_ui.py studio_link.py media_catalog.py media_catalog_test.py selftest.py integration_test.py studio_link_test.py gui_test.py
"$WORK/venv/bin/python" -c 'import app; import export_core; assert "Chapter" in export_core.SLOT_TYPES and "Component index" in export_core.SLOT_TYPES; print("GUI module import check PASS (no window opened)")'

printf '\nPackaging the macOS app...\n' 
"$WORK/venv/bin/python" -m PyInstaller --noconfirm --clean --windowed --onedir \
  --target-arch arm64 --name FolderExporter --icon "$WORK/FolderExporter.icns" \
  --add-data "$WORK/folder.png:." --add-data "$WORK/WORKFLOW_MANUAL.md:." --collect-all psd_tools --collect-all clipparse \
  "$WORK/app.py"

[[ -d "$WORK/dist/FolderExporter.app" ]] || { echo 'APP packaging failed.'; exit 1; }
mkdir -p "$HOME/Downloads"
TARGET="$HOME/Downloads/FolderExporter-AppleSilicon-v1.10.0.dmg"
N=2
while [[ -e "$TARGET" ]]; do
  TARGET="$HOME/Downloads/FolderExporter-AppleSilicon-v1.10.0-${N}.dmg"
  N=$((N + 1))
done

printf '\nCreating disk image...\n'
hdiutil create -volname FolderExporter -srcfolder "$WORK/dist/FolderExporter.app" \
  -format UDZO -ov "$TARGET"

printf '\nSUCCESS: %s\n' "$TARGET"
printf 'Open the DMG and drag FolderExporter.app to Applications.\n'
printf 'If macOS blocks the unsigned app, use System Settings -> Privacy & Security -> Open Anyway.\n'
open "$TARGET"
