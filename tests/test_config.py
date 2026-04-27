import os
import unittest

from fba_alert.config import load_config


class ConfigTests(unittest.TestCase):
    def test_source_list_concurrency_defaults_to_four(self) -> None:
        env_key = "LINGXING_SOURCE_LIST_CONCURRENCY"
        sentinel = object()
        original = os.environ.get(env_key, sentinel)
        if env_key in os.environ:
            del os.environ[env_key]
        self.addCleanup(self._restore_env, env_key, original, sentinel)

        config = load_config()

        self.assertEqual(config.lingxing.source_list_concurrency, 4)

    @staticmethod
    def _restore_env(key: str, original: object, sentinel: object) -> None:
        if original is sentinel:
            os.environ.pop(key, None)
            return
        os.environ[key] = str(original)


if __name__ == "__main__":
    unittest.main()
