---
name: dingtalk-fba-alert
description: Use when the user wants an AI to trigger the DingTalk FBA inventory alert workflow in this repository from a natural-language command, including dry-run checks and one-shot live sends for the main Libraton inventory alert.
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
When the trigger comes from a chat surface that provides the current asker's DingTalk `sender_id`, append `--notify-user-id <sender_id>` so the files are sent only to that asker instead of the repository defaults.

## Supported Trigger Phrase

Use this fixed mapping for the natural-language trigger:

- `LIBRATON库存预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all --notify-user-id <sender_id>`

If the user explicitly asks to test only, prepend `--dry-run` to the mapped command.
If the current chat context does not expose a trustworthy `sender_id`, omit `--notify-user-id` and fall back to the repository defaults.

Do not invent extra aliases or fuzzy matches. If the user asks for country-specific Libraton alerts, tell them this skill no longer exposes country trigger phrases and that scoped runs must be invoked explicitly by command.

## Delivery Rule

For the fixed natural-language trigger `LIBRATON库存预警`, treat it as an explicit live-send request.
Run the repository command that performs the built-in DingTalk delivery flow.
Do not rewrite that trigger into a dry-run summary-only path.
After the live run, the AI may report success or failure in chat, but the project remains responsible for the actual DingTalk file delivery.
When `--notify-user-id <sender_id>` is present, the repository will override its default recipient list and send only to that current asker.

## Failure Handling

- Do not silently switch from dry-run to live send, or from live send to dry-run.
- Do not use scheduler mode from this skill unless the user explicitly asks to manage scheduled execution.
- Surface missing env vars clearly.
- When the user explicitly requests a live project run, let the project send files directly through DingTalk.
- If Python dependencies are missing, tell the user which install step is needed.
- If Lingxing or Listing requests hit rate limits, tell the user whether the project retried automatically and whether the run ultimately succeeded or failed.

## Reference

For configuration details and command examples, read `references/config.md`.
