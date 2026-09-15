#!/usr/bin/env bash
# Fetch the inherited base specification into .source/ (gitignored).
#
# Pinned by default to the commit recorded in _project/base-delta.yaml. The
# base is somebody else's repository and moves on its own; if this tracked
# their HEAD, scripts/check_shape.py would report their changes as our drift
# and the guardrail would be noise. Moving the pin is a deliberate act.
#
#   ./scripts/fetch-base.sh                 # the pinned commit
#   BASE_COMMIT=HEAD ./scripts/fetch-base.sh   # whatever they have now
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_REPO="${BASE_REPO:-https://github.com/Portkey-AI/openapi.git}"
DEST="$ROOT/.source"

if [ -z "${BASE_COMMIT:-}" ]; then
  BASE_COMMIT="$(awk '/^base:/{f=1;next} f&&/^  commit:/{print $2;exit} /^[^ ]/{f=0}' \
                 "$ROOT/_project/base-delta.yaml")"
fi
[ -n "$BASE_COMMIT" ] || { echo "no base commit found or given" >&2; exit 1; }

mkdir -p "$DEST"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if [ "$BASE_COMMIT" = "HEAD" ]; then
  git clone --depth 1 "$BASE_REPO" "$tmp/base"
else
  git init -q "$tmp/base"
  git -C "$tmp/base" remote add origin "$BASE_REPO"
  git -C "$tmp/base" fetch -q --depth 1 origin "$BASE_COMMIT"
  git -C "$tmp/base" checkout -q FETCH_HEAD
fi

cp "$tmp/base/openapi.yaml" "$DEST/portkey-openapi.yaml"
git -C "$tmp/base" rev-parse HEAD > "$DEST/BASE_COMMIT"

echo "base specification -> $DEST/portkey-openapi.yaml"
echo "base commit        -> $(cat "$DEST/BASE_COMMIT")"
