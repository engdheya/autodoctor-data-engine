#!/usr/bin/env bash
# Generate the Android platform folder for this project, then apply the two settings the
# diagnostic bundle needs. Run once locally; CI runs it too so no binary Gradle wrapper has
# to be committed or hand-written.
#
#   bash tool/bootstrap_android.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORG="ai.autodoctor"
PROJECT="autodoctor_app"
APPLICATION_ID="ai.autodoctor.diagnostics"

if [[ -d "$APP_DIR/android" ]]; then
  echo "android/ already exists - nothing to do"
  exit 0
fi

command -v flutter >/dev/null || { echo "flutter is not on PATH" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

flutter create --platforms=android --org "$ORG" --project-name "$PROJECT" --template=app "$TMP/scaffold" >/dev/null
cp -r "$TMP/scaffold/android" "$APP_DIR/android"

python3 "$APP_DIR/tool/patch_android.py" "$APP_DIR" "$APPLICATION_ID"
echo "android/ created in $APP_DIR"
