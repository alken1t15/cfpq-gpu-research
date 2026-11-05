#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=${CFRA_BUILD_DIR:-"$workspace/src/cfra/build-gpu-cuda124"}
cmake -S "$workspace/src/cfra" -B "$build_dir" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-13 -DCMAKE_CXX_COMPILER=g++-13 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.4/bin/nvcc \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-11 \
  -DCMAKE_CUDA_ARCHITECTURES=86 \
  -DCUBOOL_WITH_CUDA=ON -DCUBOOL_WITH_SEQUENTIAL=OFF \
  -DCUBOOL_BUILD_TESTS=OFF -DCUBOOL_COPY_TO_PY_PACKAGE=OFF
cmake --build "$build_dir" -j2
