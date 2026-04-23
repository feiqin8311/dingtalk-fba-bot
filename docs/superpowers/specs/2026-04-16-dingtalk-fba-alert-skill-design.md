# Dingtalk FBA Alert Skill Design

## Goal

Create an OpenClaw-compatible skill that wraps the existing `dingtalk-fba-bot` Python project instead of rewriting the business logic into the skill itself.

The skill should help OpenClaw reliably:

- recognize requests related to FBA inventory alerts and DingTalk delivery
- validate local prerequisites before execution
- default to safe local verification with `--dry-run`
- run the existing project entrypoint with the correct command when the user wants an actual report run

## Scope

This design covers only the first usable local-skill version.

Included:

- a skill folder inside this repository at `skills/dingtalk-fba-alert/`
- a `SKILL.md` file with trigger guidance and execution instructions
- a small shell wrapper in `skills/dingtalk-fba-alert/scripts/run-fba-alert.sh`
- an optional reference doc for configuration and command examples

Not included:

- moving Python business logic into the skill
- changing the alerting rules
- changing the Lingxing or DingTalk integrations
- marketplace publishing automation for ClawHub
- making scheduled execution the default skill behavior

## Recommended Approach

Use the current repository as the execution layer and add a thin skill wrapper as the orchestration layer.

Why this approach:

- the Python project already contains stable business logic, tests, and an operational entrypoint
- the skill should describe when and how to run the project, not duplicate domain logic
- keeping the boundary thin reduces maintenance cost and lowers the risk of behavior drift

Alternatives considered:

1. Convert the whole repository into a skill-only implementation.
   This would blur the boundary between instructions and executable code and would make future maintenance harder.
2. Rewrite the workflow as a pure documentation skill.
   This would force the agent to reconstruct the operational flow from prose and would reduce reliability.

## Target Skill Structure

```text
skills/
└── dingtalk-fba-alert/
    ├── SKILL.md
    ├── scripts/
    │   └── run-fba-alert.sh
    └── references/
        └── config.md
```

Notes:

- `SKILL.md` is required and is the main discovery and execution guide.
- `scripts/run-fba-alert.sh` provides a stable wrapper around `python -m fba_alert.main`.
- `references/config.md` is optional but useful for keeping `SKILL.md` concise.

## Triggering Behavior

The skill should trigger for requests such as:

- run the FBA inventory alert job
- generate the DingTalk FBA report
- send the stock alert report to DingTalk users
- dry-run the Lingxing replenishment alert workflow
- check whether the inventory warning script can run locally

The skill should not trigger for:

- generic Python packaging tasks
- unrelated DingTalk bot development
- changing alert thresholds or report schema unless the user is explicitly modifying this project

## Execution Flow

When the skill is triggered, OpenClaw should follow this sequence:

1. Confirm the workspace is this repository or that the configured project path is available.
2. Check the expected files exist:
   - `.env` or another specified env file
   - `requirements.txt`
   - `fba_alert/main.py`
3. Prefer a safe validation path first:
   - run `python -m fba_alert.main --dry-run`
4. Only run a live send path when the user explicitly asks to send:
   - run `python -m fba_alert.main`
5. If the user explicitly asks for scheduler behavior, document or run:
   - `python -m fba_alert.main --schedule`

The skill should frame `--dry-run` as the default because it validates configuration and report generation without sending DingTalk messages.

## Script Design

`scripts/run-fba-alert.sh` should:

- resolve the repository root relative to the script location
- `cd` into the repository root before execution
- pass through all arguments to `python -m fba_alert.main`
- fail fast on shell errors

The wrapper should stay minimal and avoid embedding business rules.

## Error Handling

The skill instructions should tell OpenClaw to surface specific setup failures clearly:

- missing `.env`
- missing Python dependency
- missing DingTalk configuration for non-dry-run execution
- Lingxing request failures

When dry-run fails, the skill should not silently retry in live-send mode.
When live-send is requested, the skill should remind the agent to verify the user intended a real DingTalk send.

## Testing And Verification

Verification for this design should be lightweight and local:

- confirm the new skill directory and files exist
- run the wrapper in dry-run mode or at minimum run its help-safe path
- preserve the current Python unit test baseline

Primary verification command after implementation:

```bash
python -m unittest discover -s tests -v
```

If local configuration is incomplete, the skill-level validation can still confirm that:

- the wrapper points to the correct module
- the instructions correctly default to dry-run
- the file structure is discoverable by OpenClaw-compatible skill scanners

## Risks And Mitigations

Risk: the skill may depend on repository-relative paths.
Mitigation: resolve the repository root from the wrapper script itself instead of relying on the caller's current directory.

Risk: OpenClaw installation paths may differ by environment.
Mitigation: first deliver the skill inside this repository under `skills/`, which is compatible with workspace-local skill discovery patterns.

Risk: users may run live sends accidentally.
Mitigation: make `--dry-run` the documented default path and reserve live-send for explicit user intent.

## Implementation Plan Boundary

The follow-up implementation plan should cover only:

1. scaffold the skill directory
2. write `SKILL.md`
3. add the wrapper script
4. add a small reference doc if needed
5. validate file structure and current tests

This is intentionally a narrow first version. ClawHub publishing metadata can be added in a later iteration once the local skill is working.
