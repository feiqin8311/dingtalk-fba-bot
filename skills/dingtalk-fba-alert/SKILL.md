---
name: dingtalk-fba-alert
description: Use when the user wants to run, dry-run, or verify the DingTalk FBA inventory alert workflow in this repository and then let OpenClaw handle delivery of the generated result.
---

# Dingtalk FBA Alert

This skill wraps the existing `dingtalk-fba-bot` project instead of reimplementing its business logic.
When OpenClaw uses this skill, it should run once for the current user request and should not start scheduler mode.
OpenClaw should handle delivery of the generated report or summary after the project finishes.

## Use This Skill For

- running the inventory alert workflow locally
- generating the Excel warning report
- checking whether the alert job can run with `--dry-run`
- producing results that OpenClaw can inspect and send through its own messaging flow

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

Prefer the safe path first:

```bash
bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run
```

This validates configuration, Lingxing access, and report generation without sending DingTalk messages.
Use it as a single run for the current request.

## Supported Scope Phrases

Use these fixed mappings when the user asks for a specific Libraton inventory alert:

- `LIBRATON库存预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope all`
- `LIBRATON库存美国预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope us`
- `LIBRATON库存加拿大预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope ca`
- `LIBRATON库存日本预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope jp`
- `LIBRATON库存欧洲预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --dry-run --scope eu`

For this first version, do not invent extra aliases or fuzzy matches. If the user asks for another country, explain that only `总表/美国/加拿大/日本/欧洲` are supported.

## Delivery Rule

Do not use the live DingTalk send path from this skill.
Run the project, collect the report or summary result, then let OpenClaw send the final message.

## Failure Handling

- Do not silently switch from dry-run to any live send path.
- Do not use scheduler mode from this skill. This skill is for one-shot execution only.
- Surface missing env vars clearly.
- If the user wants a message sent after execution, OpenClaw should handle delivery instead of delegating it back to the project.
- If Python dependencies are missing, tell the user which install step is needed.

## Reference

For configuration details and command examples, read `references/config.md`.
