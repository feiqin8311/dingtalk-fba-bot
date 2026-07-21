---
name: dingtalk-fba-alert
description: Company FBA inventory alert via this repo's HTTP API (or CLI). Fixed phrases LIBRATON/EZARC/YPLUS 库存预警; personal notify by userId. YidaLab uses HTTP mode=self — not shell scripts.
---

# Dingtalk FBA Alert

Business logic lives in this repository (`fba_alert/`). Agents should **not** reimplement it.

## Preferred path (YidaLab)

YidaLab calls the **HTTP API** on the same process as the weekly scheduler:

```bash
python -m fba_alert.main --schedule   # cron + :8090 API
```

```http
POST /v1/alerts/run
Authorization: Bearer <FBA_ALERT_API_TOKEN>
{ "scope": "all", "mode": "self", "notify_user_ids": ["<dingtalk-user-id>"] }
```

- `mode=self` + `notify_user_ids`: only that person (YidaLab injects sender / channel Owner).
- Do **not** shell into this repo or use deleted `scripts/` wrappers from agents.
- See repository README «HTTP API».

## Fixed trigger phrases

| Phrase | scope |
| ------ | ----- |
| `LIBRATON库存预警` | `all` (Libraton full) |
| `EZARC库存预警` | `ezarc` |
| `YPLUS库存预警` | `yplus` |

No site menu. Optional dry-run: `mode=dry_run` or CLI `--dry-run`.

## Local CLI (ops / debug only)

```bash
python -m fba_alert.main --dry-run --scope all
python -m fba_alert.main --scope ezarc --notify-user-id <userId>
python -m fba_alert.main --scope yplus --upload-only
```

Requires `.env` at repo root (`LINGXING_*`, `DINGTALK_*`, and for API `FBA_ALERT_API_TOKEN`).

## Scope notes

- `all`: Libraton main + store reports (with override user, main only to that user).
- `us` / `ca` / `jp` / `eu`: Libraton region only.
- `ezarc` / `yplus` (+ `-test`): brand main + stores (same override rule).

## Failure handling

- Do not silently switch dry-run ↔ live.
- Missing env / token: say what is missing.
- Weekly broadcast stays on `--schedule` cron; chat triggers use `mode=self` only.
