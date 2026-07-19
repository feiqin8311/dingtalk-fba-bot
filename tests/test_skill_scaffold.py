import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "dingtalk-fba-alert"


class SkillScaffoldTests(unittest.TestCase):
    def test_skill_files_exist(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").exists())
        self.assertTrue((SKILL_ROOT / "scripts" / "run-fba-alert.sh").exists())
        self.assertTrue((SKILL_ROOT / "references" / "config.md").exists())

    def test_skill_runner_uses_configured_or_current_python(self) -> None:
        runner_text = (SKILL_ROOT / "scripts" / "run-fba-alert.sh").read_text(encoding="utf-8")

        self.assertIn("python_bin=", runner_text)
        self.assertIn("DINGTALK_FBA_BOT_PYTHON", runner_text)
        self.assertIn("python3", runner_text)
        self.assertIn('exec env \\', runner_text)
        self.assertIn('  "${python_bin}" -m fba_alert.main "$@"', runner_text)

    def test_skill_runner_passes_arguments_to_configured_python(self) -> None:
        runner_path = SKILL_ROOT / "scripts" / "run-fba-alert.sh"
        with tempfile.TemporaryDirectory() as tmp_dir:
            capture_path = Path(tmp_dir) / "args.txt"
            fake_python = Path(tmp_dir) / "python"
            fake_python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$RUNNER_CAPTURE"\n', encoding="utf-8")
            fake_python.chmod(0o755)
            env = os.environ | {
                "DINGTALK_FBA_BOT_PYTHON": str(fake_python),
                "RUNNER_CAPTURE": str(capture_path),
            }

            subprocess.run(
                ["bash", str(runner_path), "--dry-run", "--scope", "ezarc"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
            )

            self.assertEqual(capture_path.read_text(encoding="utf-8").splitlines(), ["-m", "fba_alert.main", "--dry-run", "--scope", "ezarc"])

    def test_skill_instructions_do_not_expose_scheduler_mode(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_text = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        self.assertNotIn("--schedule", skill_text)
        self.assertNotIn("--schedule", reference_text)
        self.assertIn("run once", skill_text)

    def test_skill_instructions_use_live_delivery_for_main_trigger(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_text = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")
        skill_text_lower = skill_text.lower()
        reference_text_lower = reference_text.lower()

        self.assertIn("For a real trigger request such as `LIBRATON库存预警`, use the live path", skill_text)
        self.assertIn("`LIBRATON库存预警` -> `bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all --notify-user-id <sender_id>`", skill_text)
        self.assertIn("--notify-user-id <sender_id>", skill_text)
        self.assertIn("When the user explicitly requests a live project run, let the project send files directly through DingTalk.", skill_text)
        self.assertNotIn("OpenClaw should handle delivery", skill_text)
        self.assertNotIn("do not use the live dingtalk send path", skill_text_lower)
        self.assertIn("bash skills/dingtalk-fba-alert/scripts/run-fba-alert.sh --scope all --notify-user-id <sender_id>", reference_text)
        self.assertIn("project will use its built-in DingTalk delivery flow", reference_text)
        self.assertNotIn("OpenClaw sends the final message", reference_text)
        self.assertNotIn("do not use the live dingtalk send path", reference_text_lower)

    def test_skill_documents_supported_trigger_aliases_and_full_scope_set(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_text = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        for trigger in ("LIBRATON库存预警", "EZARC库存预警", "YPLUS库存预警", "EZARC库存预警测试", "YPLUS库存预警测试"):
            self.assertIn(trigger, skill_text)
        self.assertNotIn("LIBRATON库存美国预警", skill_text)
        self.assertNotIn("LIBRATON库存加拿大预警", skill_text)
        self.assertNotIn("LIBRATON库存日本预警", skill_text)
        self.assertNotIn("LIBRATON库存欧洲预警", skill_text)
        self.assertIn("--scope all", skill_text)
        for scope in ("all", "us", "ca", "jp", "eu", "ezarc", "yplus", "ezarc-test", "yplus-test"):
            self.assertIn(f"--scope {scope}", reference_text)
        self.assertIn("--upload-only", skill_text)
        self.assertIn("--upload-only", reference_text)

    def test_skill_runner_passes_live_send_arguments_through(self) -> None:
        ops_runner_text = (SKILL_ROOT / "scripts" / "run-fba-alert.sh").read_text(encoding="utf-8")

        self.assertIn('  "${python_bin}" -m fba_alert.main "$@"', ops_runner_text)
        self.assertNotIn("OpenClaw live send requires --notify-user-id", ops_runner_text)


if __name__ == "__main__":
    unittest.main()
