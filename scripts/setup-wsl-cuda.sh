#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$workspace/downloads"
keyring="$workspace/downloads/cuda-keyring_1.1-1_all.deb"
curl -fL --retry 2 -o "$keyring" \
  https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
sha256sum "$keyring"
dpkg -i "$keyring"
apt-get update
# Compiler, runtime headers and CCCL only; no Linux NVIDIA driver in WSL.
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  cuda-nvcc-12-4 cuda-cudart-dev-12-4 cuda-cccl-12-4 cuda-driver-dev-12-4
/usr/local/cuda-12.4/bin/nvcc --version
