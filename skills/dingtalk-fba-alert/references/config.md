# Dingtalk FBA Alert Config

This skill assumes the current workspace is the `dingtalk-fba-bot` repository.

## Required Files

- `.env`
- `requirements.txt`
- `fba_alert/main.py`

## Common Commands

Dry-run:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run
```

Dry-run by scope:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope all
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope us
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope ca
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope jp
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope eu
```

## Important Env Vars

- `LINGXING_SID_LIST`
- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_ROBOT_CODE`
- `DINGTALK_USER_IDS`

## Notes

- `--dry-run` is the default safe path because it generates the report without sending DingTalk messages.
- `--scope all` runs the full Libraton flow and generates the main report.
- `--scope us|ca|jp|eu` runs only the requested region and skips the main report.
- This skill is for run-once execution only and should not use scheduler mode.
- OpenClaw sends the final message after the project run completes.
- From this skill, do not use the live DingTalk send path.
