FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_FALLBACK_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOSTS="pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com pypi.org files.pythonhosted.org"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN set -eux; \
    pip install --upgrade pip; \
    for index_url in "${PIP_INDEX_URL}" "${PIP_EXTRA_INDEX_URL}" "${PIP_FALLBACK_INDEX_URL}"; do \
        trusted_host="$(printf '%s' "${index_url}" | sed -E 's#^[a-zA-Z]+://([^/]+)/?.*$#\1#')"; \
        if pip install -r /app/requirements.txt -i "${index_url}" --trusted-host "${trusted_host}"; then \
            exit 0; \
        fi; \
    done; \
    echo "pip install failed for all configured indexes"; \
    exit 1

COPY fba_alert /app/fba_alert
COPY .env.example /app/.env.example
COPY README.md /app/README.md

CMD ["python", "-m", "fba_alert.main", "--schedule"]
