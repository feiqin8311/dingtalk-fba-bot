#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../.." && pwd)"
python_bin="/home/yida/miniconda3/envs/dingtalk-bot/bin/python"

if [[ ! -x "${python_bin}" ]]; then
  echo "dingtalk-bot env python does not exist: ${python_bin}" >&2
  exit 1
fi

cd "${repo_root}"
exec env \
  -u HTTP_PROXY \
  -u HTTPS_PROXY \
  -u ALL_PROXY \
  -u http_proxy \
  -u https_proxy \
  -u all_proxy \
  -u NO_PROXY \
  -u no_proxy \
  PYTHONUNBUFFERED=1 \
  "${python_bin}" -m fba_alert.main "$@"
