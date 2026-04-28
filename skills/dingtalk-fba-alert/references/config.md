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

Live send:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh
```

Dry-run by scope:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope all
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope us
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope ca
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope jp
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope eu
```

Live send by scope:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope us
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope ca
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope jp
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope eu
```

Live send to the current asker only:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all --notify-user-id <sender_id>
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope us --notify-user-id <sender_id>
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope ca --notify-user-id <sender_id>
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope jp --notify-user-id <sender_id>
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope eu --notify-user-id <sender_id>
```

## Important Env Vars

- `LINGXING_SID_LIST`
- `LINGXING_LISTING_CONCURRENCY`
- `LINGXING_SOURCE_LIST_CONCURRENCY`
- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_ROBOT_CODE`
- `DINGTALK_USER_IDS`

## Notes

- `--dry-run` is the safe verification path because it generates the report without sending DingTalk messages.
- No `--dry-run` means the project will use its built-in DingTalk delivery flow.
- The fixed trigger `LIBRATON库存预警` should map to `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all --notify-user-id <sender_id>` when the current asker's DingTalk `sender_id` is available.
- `--notify-user-id` overrides the repository's default recipient list for that one run and can be repeated to target multiple explicit recipients.
- `--scope all` runs the full Libraton flow and generates the main report.
- `--scope us|ca|jp|eu` runs only the requested region and skips the main report.
- This skill is for run-once execution from a local repository checkout. Only use scheduler mode if the user explicitly asks to manage scheduling.
- For `LIBRATON库存预警`, treat the run itself as the live-send request and let the repository deliver the files through DingTalk.
- `Listing` and `SourceList` requests may hit Lingxing rate limits. The project now retries and can reduce concurrency automatically before giving up.
- Current alert priority is `C > A > B`, so `FBA库存=0 且 FBA在途>0` takes precedence over A/B rules.
