---
name: dingtalk-fba-alert
description: Use when the user wants an AI to trigger the DingTalk FBA inventory alert workflow in this repository from a natural-language command, including dry-run checks, one-shot live sends, or scope-specific Libraton alerts.
---

# Dingtalk FBA Alert

This skill wraps the existing `dingtalk-fba-bot` project instead of reimplementing its business logic.
Any AI that installs this skill should treat the repository itself as the execution engine:
- the AI recognizes the user's trigger phrase
- the AI runs the project command that matches the request
- the project generates reports and sends DingTalk files through its own built-in delivery flow when live mode is used

For conversational AI usage, prefer run once / one-shot execution. Do not start scheduler mode unless the user explicitly asks to manage long-running scheduling.

## Use This Skill For

- triggering the inventory alert workflow from a natural-language command
- generating the Excel warning report with `--dry-run`
- performing a one-shot live send through the project's own DingTalk logic
- handling scope-specific Libraton alert requests such as US, CA, JP, and EU
- operating the repo from a local checkout

## Do Not Use This Skill For

- unrelated DingTalk bot development
- changing the alert rules or Python implementation unless the user explicitly asks to modify this project

## Required Checks

Before running anything, confirm these files exist in the workspace root:

- `.env` or another env file path provided by the user
- `requirements.txt`
- `fba_alert/main.py`

If `.env` is missing, stop and tell the user what is missing.

## Default Execution Path

Choose the path based on user intent:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run
```

Use `--dry-run` when the user asks to test, verify, inspect output, or avoid DingTalk sends.

For a real trigger request such as `LIBRATON库存预警`, use the live path:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh
```

This project already knows how to generate the report and send the correct files to the configured recipients.

## Supported Scope Phrases

Use these fixed mappings when the user asks for a specific Libraton inventory alert:

- `LIBRATON库存预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all`
- `LIBRATON库存美国预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope us`
- `LIBRATON库存加拿大预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope ca`
- `LIBRATON库存日本预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope jp`
- `LIBRATON库存欧洲预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope eu`

If the user explicitly asks to test only, prepend `--dry-run` to the mapped command.

Do not invent extra aliases or fuzzy matches. If the user asks for another country, explain that only `总表/美国/加拿大/日本/欧洲` are supported.

## Delivery Rule

OpenClaw should handle delivery when the user wants the AI to send the final conversational response.
For this skill, do not use the live dingtalk send path as a substitute for the AI's own reply channel unless the user explicitly asks to run the repository's built-in send flow.
When the user explicitly requests a live project run, let the project send files directly through DingTalk.
The AI should not replace the project's delivery logic with its own messaging flow.

## Failure Handling

- Do not silently switch from dry-run to live send, or from live send to dry-run.
- Do not use scheduler mode from this skill unless the user explicitly asks to manage scheduled execution.
- Surface missing env vars clearly.
- If the user wants the standard DingTalk file delivery, use the live project command instead of trying to simulate it in the AI response.
- If Python dependencies are missing, tell the user which install step is needed.
- If Lingxing or Listing requests hit rate limits, tell the user whether the project retried automatically and whether the run ultimately succeeded or failed.

## Reference

For configuration details and command examples, read `references/config.md`.
