from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "dingtalk-fba-alert"


class SkillScaffoldTests(unittest.TestCase):
    def test_skill_files_exist(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").exists())
        self.assertTrue((SKILL_ROOT / "scripts" / "run-fba-alert.sh").exists())
        self.assertTrue((SKILL_ROOT / "references" / "config.md").exists())

    def test_skill_runner_uses_dingtalk_bot_conda_env(self) -> None:
        runner_text = (SKILL_ROOT / "scripts" / "run-fba-alert.sh").read_text(encoding="utf-8")

        self.assertIn("conda", runner_text)
        self.assertIn("run -n dingtalk-bot", runner_text)
        self.assertIn("python -m fba_alert.main", runner_text)

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

    def test_skill_only_documents_main_trigger_phrase(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_text = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")

        self.assertIn("LIBRATON库存预警", skill_text)
        self.assertNotIn("LIBRATON库存美国预警", skill_text)
        self.assertNotIn("LIBRATON库存加拿大预警", skill_text)
        self.assertNotIn("LIBRATON库存日本预警", skill_text)
        self.assertNotIn("LIBRATON库存欧洲预警", skill_text)
        self.assertIn("--scope all", skill_text)
        self.assertIn("--scope eu", reference_text)

    def test_skill_documents_japan_scoped_trigger_for_ops_wrapper(self) -> None:
        ops_skill_text = Path("/home/yida/.openclaw/workspace-ops/skills/dingtalk-fba-alert/SKILL.md").read_text(encoding="utf-8")
        ops_soul_text = Path("/home/yida/.openclaw/workspace-ops/SOUL.md").read_text(encoding="utf-8")
        ops_reference_text = Path("/home/yida/.openclaw/workspace-ops/skills/dingtalk-fba-alert/references/config.md").read_text(encoding="utf-8")

        self.assertIn("5. LIBRATON库存预警-日本", ops_skill_text)
        self.assertIn("5. LIBRATON库存预警-日本", ops_soul_text)
        self.assertIn("LIBRATON库存预警-日本", ops_reference_text)
        self.assertIn("--scope jp", ops_skill_text)
        self.assertIn("--scope jp", ops_reference_text)

    def test_ops_wrapper_rejects_live_send_without_notify_override(self) -> None:
        ops_runner_text = Path("/home/yida/.openclaw/workspace-ops/skills/dingtalk-fba-alert/scripts/run-fba-alert.sh").read_text(encoding="utf-8")

        self.assertIn("--notify-user-id", ops_runner_text)
        self.assertIn("--dry-run", ops_runner_text)
        self.assertIn("OpenClaw live send requires --notify-user-id", ops_runner_text)


if __name__ == "__main__":
    unittest.main()
