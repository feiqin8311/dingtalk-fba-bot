import importlib
import sys
import unittest


class ScopeTests(unittest.TestCase):
    def test_parse_all_scope(self) -> None:
        from fba_alert.scopes import AlertScope

        self.assertEqual(AlertScope.parse("all"), AlertScope.ALL)

    def test_parse_rejects_unknown_scope(self) -> None:
        from fba_alert.scopes import AlertScope

        with self.assertRaises(ValueError):
            AlertScope.parse("mx")

    def test_eu_scope_resolves_both_supported_eu_stores(self) -> None:
        from fba_alert.scopes import AlertScope, resolve_scope_seller_names

        seller_map = {
            "1446": "Libraton EU-UK",
            "1448": "Libraton EU-DE",
            "1443": "Libraton NA-US",
        }

        self.assertEqual(
            resolve_scope_seller_names(AlertScope.EU, seller_map),
            {"Libraton EU-UK", "Libraton EU-DE"},
        )


class MainArgTests(unittest.TestCase):
    def test_parse_args_reads_scope(self) -> None:
        sys.modules.pop("fba_alert", None)
        sys.modules.pop("fba_alert.main", None)
        sys.modules.pop("fba_alert.config", None)
        sys.modules.pop("fba_alert.lingxing", None)
        sys.modules.pop("fba_alert.utils", None)
        sys.modules.pop("fba_alert.dingtalk", None)
        parse_args = importlib.import_module("fba_alert.main").parse_args

        old_argv = sys.argv[:]
        self.addCleanup(lambda: setattr(sys, "argv", old_argv))
        sys.argv = ["prog", "--scope", "jp"]

        args = parse_args()

        self.assertEqual(args.scope, "jp")


if __name__ == "__main__":
    unittest.main()
