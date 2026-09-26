#!/usr/bin/env bash
# AFLA GPU check: confirms the NVIDIA GPU is usable from WSL2 and from Docker containers.
# Changes nothing on the system. Step 3 downloads a small CUDA test image (~150 MB, removed afterwards).
# Usage: bash afla-gpu-check.sh

CUDA_IMG="nvidia/cuda:12.4.1-base-ubuntu22.04"
ok(){ printf '  [OK]   %s\n' "$1"; }; bad(){ printf '  [FAIL] %s\n' "$1"; FAIL=1; }
FAIL=0

echo "1. GPU visible inside WSL (Windows NVIDIA driver provides this; no Linux driver should be installed)"
if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
  ok "$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader)"
  nvidia-smi | grep -m1 'CUDA Version' | sed 's/^/         /'
else
  bad "nvidia-smi fails in WSL → update the Windows NVIDIA driver (Game Ready/Studio), then run 'wsl --shutdown' in PowerShell"
fi
dpkg -l 2>/dev/null | grep -E '^ii +nvidia-driver|^ii +libnvidia-compute' | awk '{print "  [WARN] Linux NVIDIA driver package inside WSL: "$2" (can break WSL GPU support)"}'

echo "2. Docker reachable from WSL (Docker Desktop → Settings → Resources → WSL integration → Ubuntu ON)"
if docker info >/dev/null 2>&1; then
  ok "Docker $(docker version --format '{{.Server.Version}}') ($(docker info --format '{{.OperatingSystem}}'))"
else
  bad "docker not reachable from Ubuntu"; echo "Stopping: fix Docker first."; exit 1
fi

echo "3. GPU inside a container (docker run --gpus all)"
had_img=$(docker images -q "$CUDA_IMG")
if out=$(docker run --rm --gpus all "$CUDA_IMG" nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1); then
  ok "container sees: $out"
else
  bad "container cannot use the GPU:"; echo "$out" | tail -n 3 | sed 's/^/         /'
  echo "         Fix: update Docker Desktop, ensure 'Use the WSL 2 based engine' is on, restart Docker Desktop."
fi
[ -z "$had_img" ] && docker rmi "$CUDA_IMG" >/dev/null 2>&1

echo "4. Resources Docker Desktop gives WSL"
echo "  CPUs: $(docker info --format '{{.NCPU}}')   Memory: $(docker info --format '{{.MemTotal}}' | awk '{printf "%.0f GB", $1/1073741824}')"
echo "  (Plan target: ~14 CPUs and ~52 GB, set via C:\\Users\\<you>\\.wslconfig)"

echo
[ $FAIL -eq 0 ] && echo "RESULT: GPU ready for DeepVariant-GPU and SpliceAI containers." || echo "RESULT: fix the [FAIL] items above, then re-run."
