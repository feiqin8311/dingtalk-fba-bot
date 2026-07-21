from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "dingtalk-fba-alert"


class SkillScaffoldTests(unittest.TestCase):
    def test_skill_md_exists_without_scripts_or_references(self) -> None:
        self.assertTrue((SKILL_ROOT / "SKILL.md").exists())
        self.assertFalse((SKILL_ROOT / "scripts").exists())
        self.assertFalse((SKILL_ROOT / "references").exists())

    def test_skill_prefers_http_api_not_shell_wrapper(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("HTTP", skill_text)
        self.assertIn("/v1/alerts/run", skill_text)
        self.assertIn("mode=self", skill_text)
        self.assertNotIn("run-fba-alert.sh", skill_text)
        self.assertNotIn("skills/dingtalk-fba-alert/scripts", skill_text)
        self.assertNotIn("references/config.md", skill_text)

    def test_skill_documents_fixed_triggers(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for trigger in (
            "LIBRATON库存预警",
            "EZARC库存预警",
            "YPLUS库存预警",
        ):
            self.assertIn(trigger, skill_text)
        self.assertNotIn("库存预警测试", skill_text)
        self.assertIn("`all`", skill_text)
        self.assertIn("`ezarc`", skill_text)
        self.assertIn("`yplus`", skill_text)
        # No region-menu aliases
        self.assertNotIn("LIBRATON库存美国预警", skill_text)
        self.assertNotIn("请选择站点", skill_text)

    def test_skill_documents_cli_fallback(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python -m fba_alert.main", skill_text)
        self.assertIn("--notify-user-id", skill_text)
        self.assertIn("--dry-run", skill_text)


if __name__ == "__main__":
    unittest.main()
