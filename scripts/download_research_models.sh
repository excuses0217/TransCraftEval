#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
model_dir="$project_dir/models/insightface"
archive=$(mktemp "${TMPDIR:-/tmp}/buffalo_l.XXXXXX.zip")
trap 'rm -f "$archive"' EXIT HUP INT TERM
mkdir -p "$model_dir"

proxy=$(git config --global --get https.proxy 2>/dev/null || true)
if [ -n "$proxy" ]; then
  set -- --proxy "$proxy"
else
  set --
fi

curl "$@" -fL --retry 3 --output "$archive" \
  "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

archive_sha=$(shasum -a 256 "$archive" | awk '{print $1}')
if [ "$archive_sha" != "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f" ]; then
  echo "Checksum mismatch for Buffalo-L archive" >&2
  exit 1
fi

unzip -jo "$archive" w600k_r50.onnx -d "$model_dir"
model_sha=$(shasum -a 256 "$model_dir/w600k_r50.onnx" | awk '{print $1}')
if [ "$model_sha" != "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43" ]; then
  rm -f "$model_dir/w600k_r50.onnx"
  echo "Checksum mismatch for ArcFace model" >&2
  exit 1
fi

echo "Research-only ArcFace model installed in $model_dir"
echo "Review InsightFace's pretrained-model license before any production use."
