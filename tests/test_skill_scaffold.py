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

    def test_skill_instructions_delegate_message_delivery_to_openclaw(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_text = (SKILL_ROOT / "references" / "config.md").read_text(encoding="utf-8")
        skill_text_lower = skill_text.lower()

        self.assertIn("OpenClaw should handle delivery", skill_text)
        self.assertIn("do not use the live dingtalk send path", skill_text_lower)
        self.assertIn("OpenClaw sends the final message", reference_text)

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


if __name__ == "__main__":
    unittest.main()
