#!/usr/bin/env bash
# Run from Ubuntu WSL; paths are derived from this script's location.
set -euo pipefail

workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir="$workspace/src/cfra"
build_dir="$source_dir/build-cpu-gcc13"

g++-13 --version
cmake --version
cmake -S "$source_dir" -B "$build_dir" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-13 \
  -DCMAKE_CXX_COMPILER=g++-13 \
  -DCUBOOL_WITH_CUDA=OFF \
  -DCUBOOL_COPY_TO_PY_PACKAGE=OFF \
  -DCUBOOL_BUILD_TESTS=OFF
cmake --build "$build_dir" -j4

cd "$source_dir"
# Windows Git may check out CRLF. Normalize only the streamed script and
# redirect its hardcoded executable path; keep all upstream checks unchanged.
bash <(sed -e 's/\r$//' -e 's|^CFRA=./build/cfra$|CFRA=./build-cpu-gcc13/cfra|' ci/test.sh)
