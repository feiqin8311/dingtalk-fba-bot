#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../.." && pwd)"
configured_python="${DINGTALK_FBA_BOT_PYTHON:-}"

if [[ -f "${repo_root}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${repo_root}/.env"
  set +a
fi

python_bin="${configured_python:-${DINGTALK_FBA_BOT_PYTHON:-python3}}"

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "python executable not found: ${python_bin}" >&2
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
