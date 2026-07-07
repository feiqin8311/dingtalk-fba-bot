# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python DingTalk FBA alert service. Core source code lives in `fba_alert/`: `main.py` is the CLI entrypoint, `application.py` coordinates the workflow, `lingxing.py` calls Lingxing APIs, `alerts.py` classifies alert records, `report.py` writes Excel files, and `dingtalk.py` / `dingpan.py` handle delivery. Tests live in `tests/`. Operational wrappers and agent-facing commands live under `skills/dingtalk-fba-alert/`. Runtime output is written to `reports/YYYY-MM-DD/`.

## Build, Test, and Development Commands

Create configuration from the example before running:

```bash
cp .env.example .env
```

Run a safe local report generation:

```bash
python -m fba_alert.main --dry-run
```

Run a real send only when intended:

```bash
python -m fba_alert.main --scope all
```

Start the Docker scheduler:

```bash
docker compose up -d --build
docker logs -f dingtalk-fba-bot
```

Run tests with:

```bash
python -m pytest tests
```

## Coding Style & Naming Conventions

Use Python 3.11 syntax, 4-space indentation, explicit type hints where practical, and small functions with direct names. Keep business thresholds in `store_policies.py`; avoid scattering alert constants through workflow code. Use snake_case for modules, functions, and variables. Prefer existing helpers in `utils.py`, `scopes.py`, and `store_policies.py` before adding new abstractions.

## Testing Guidelines

Tests use `pytest` and standard `unittest` async test cases. Add or update focused tests in `tests/test_*.py` when changing alert rules, Lingxing retry behavior, report grouping, DingTalk/DingPan delivery, or scope selection. Prefer deterministic fake clients over live API calls.

## Commit & Pull Request Guidelines

Git history uses concise imperative messages, often with prefixes such as `fix:` and `feat:`. Keep commits scoped to one behavior change. Pull requests should describe the operational impact, list the command used for verification, and call out whether the change can send DingTalk messages or alter DingPan placement.

## Security & Configuration Tips

Do not commit `.env`, access tokens, DingTalk secrets, or generated reports. Use `.env.example` for documenting required variables. Use `--dry-run` for validation unless the task explicitly requires upload or message delivery.
