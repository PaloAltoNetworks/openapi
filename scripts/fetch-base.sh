#!/usr/bin/env bash
# Fetch the inherited base specification into .source/ (gitignored).
#
# Only needed to re-run scripts/build.py. Nothing in CI depends on it: the
# generated openapi.yaml is committed, and check.py validates that file.
set -euo pipefail

BASE_REPO="${BASE_REPO:-https://github.com/Portkey-AI/openapi.git}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/.source"

mkdir -p "$DEST"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone --depth 1 "$BASE_REPO" "$tmp/base"
cp "$tmp/base/openapi.yaml" "$DEST/portkey-openapi.yaml"
git -C "$tmp/base" rev-parse HEAD > "$DEST/BASE_COMMIT"

echo "base specification -> $DEST/portkey-openapi.yaml"
echo "base commit        -> $(cat "$DEST/BASE_COMMIT")"
