import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).parents[1]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class VersionInfoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env_patch = patch.dict(os.environ, {"DATA_DIR": cls.tmp.name})
        cls.env_patch.start()
        name = "lan_clipboard_version_test_app"
        spec = importlib.util.spec_from_file_location(name, ROOT / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[name] = cls.module
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        cls.env_patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.module._version_cache.update(expires=0.0, value=None)
        self.metadata = {
            "branch": "main",
            "sha": "a" * 40,
            "short_sha": "a" * 7,
            "commit_date": "2026-10-20T12:00:00Z",
            "build_time": "2026-10-21T12:00:00Z",
            "repository": "Crazy1wh/lan-clipboard",
            "repository_url": "https://github.com/Crazy1wh/lan-clipboard",
        }

    def test_database_is_initialized_only_in_temporary_data_dir(self):
        self.assertTrue(self.module.DB_PATH.is_file())
        self.assertEqual(self.module.DB_PATH.parent, Path(self.tmp.name))

    def test_github_comparison_states_do_not_false_positive(self):
        cases = {
            "behind": ("available", True),
            "ahead": ("ahead", False),
            "diverged": ("diverged", False),
            "identical": ("current", False),
        }
        for github_status, expected in cases.items():
            with self.subTest(github_status=github_status):
                payload = {
                    "status": github_status,
                    "ahead_by": 2 if github_status == "ahead" else 0,
                    "behind_by": 3 if github_status == "behind" else 0,
                }
                seen = []

                def fake_urlopen(request, timeout):
                    seen.append((request.full_url, timeout))
                    return FakeResponse(payload)

                with patch.object(self.module, "read_build_metadata", return_value=self.metadata), patch.object(
                    self.module, "urlopen", side_effect=fake_urlopen
                ):
                    result = self.module._uncached_version_info()
                self.assertEqual(result["update"]["status"], expected[0])
                self.assertEqual(result["update"]["available"], expected[1])
                self.assertIn("/compare/main..." + "a" * 40, seen[0][0])
                self.assertLessEqual(seen[0][1], 10)

    def test_unavailable_is_unknown_not_current(self):
        with patch.object(self.module, "read_build_metadata", return_value=self.metadata), patch.object(
            self.module, "urlopen", side_effect=URLError("offline")
        ):
            result = self.module._uncached_version_info()
        self.assertEqual(result["update"]["status"], "unknown")
        self.assertFalse(result["update"]["available"])

    def test_ttl_cache_includes_failed_checks(self):
        with patch.object(self.module, "read_build_metadata", return_value=self.metadata), patch.object(
            self.module, "urlopen", side_effect=URLError("offline")
        ) as mocked:
            first = self.module.get_version_info()
            second = self.module.get_version_info()
        self.assertIs(first, second)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(second["update"]["status"], "unknown")

    def test_cache_lock_collapses_concurrent_refreshes(self):
        calls = []

        def slow_result():
            calls.append(1)
            time.sleep(0.03)
            return {"update": {"status": "unknown", "available": False}}

        with patch.object(self.module, "_uncached_version_info", side_effect=slow_result):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.module.get_version_info(), range(8)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(result is results[0] for result in results))

    def test_build_metadata_works_without_git(self):
        build_env = {
            "BUILD_REPOSITORY": "Crazy1wh/lan-clipboard",
            "BUILD_BRANCH": "release/test",
            "BUILD_SHA": "b" * 40,
            "BUILD_COMMIT_DATE": "2026-10-01T01:02:03Z",
            "BUILD_TIME": "2026-10-02T04:05:06Z",
        }
        with patch.dict(os.environ, build_env), patch.object(self.module, "_run_git", return_value=None):
            metadata = self.module.read_build_metadata()
        self.assertEqual(metadata["branch"], "release/test")
        self.assertEqual(metadata["short_sha"], "b" * 7)
        self.assertEqual(metadata["commit_date"], build_env["BUILD_COMMIT_DATE"])
        self.assertEqual(metadata["build_time"], build_env["BUILD_TIME"])

    def test_repository_falls_back_to_origin_and_rejects_non_github_url(self):
        def git_value(*args):
            values = {
                ("log", "-1", "--format=%H%n%cI"): "c" * 40 + "\n2026-10-03T00:00:00Z",
                ("branch", "--show-current"): "main",
                ("remote", "get-url", "origin"): "git@github.com:Crazy1wh/lan-clipboard.git",
            }
            return values.get(args)

        with patch.dict(os.environ, {"DATA_DIR": self.tmp.name}, clear=True), patch.object(
            self.module, "_run_git", side_effect=git_value
        ):
            metadata = self.module.read_build_metadata()
        self.assertEqual(metadata["repository"], "Crazy1wh/lan-clipboard")
        self.assertIsNone(self.module._github_repository("https://example.com/evil/repo"))


if __name__ == "__main__":
    unittest.main()
