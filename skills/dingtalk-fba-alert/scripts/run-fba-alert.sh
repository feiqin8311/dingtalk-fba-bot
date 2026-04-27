#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../.." && pwd)"
conda_bin="/home/yida/miniconda3/condabin/conda"

cd "${repo_root}"
"${conda_bin}" run -n dingtalk-bot env \
  -u HTTP_PROXY \
  -u HTTPS_PROXY \
  -u ALL_PROXY \
  -u http_proxy \
  -u https_proxy \
  -u all_proxy \
  -u NO_PROXY \
  -u no_proxy \
  PYTHONUNBUFFERED=1 \
  python -m fba_alert.main "$@"
