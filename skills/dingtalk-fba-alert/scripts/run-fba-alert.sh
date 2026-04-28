#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../.." && pwd)"
python_bin="${DINGTALK_FBA_BOT_PYTHON:-}"
conda_env_name="${DINGTALK_FBA_BOT_CONDA_ENV:-dingtalk-bot}"

if [[ -z "${python_bin}" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  python_bin="${CONDA_PREFIX}/bin/python"
fi

if [[ -z "${python_bin}" && -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  python_bin="${VIRTUAL_ENV}/bin/python"
fi

if [[ -z "${python_bin}" && -n "$(command -v conda || true)" ]]; then
  conda_base="$(conda info --base 2>/dev/null || true)"
  if [[ -n "${conda_base}" && -x "${conda_base}/envs/${conda_env_name}/bin/python" ]]; then
    python_bin="${conda_base}/envs/${conda_env_name}/bin/python"
  fi
fi

if [[ -z "${python_bin}" ]]; then
  python_bin="$(command -v python3 || true)"
fi

if [[ -z "${python_bin}" ]]; then
  python_bin="$(command -v python || true)"
fi

if [[ -z "${python_bin}" || ! -x "${python_bin}" ]]; then
  echo "No runnable Python found. Set DINGTALK_FBA_BOT_PYTHON or activate an environment with python3/python." >&2
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
