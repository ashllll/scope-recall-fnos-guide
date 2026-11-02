import unittest

import release_check


class ReleaseCheckTests(unittest.TestCase):
    def test_numeric_version_order(self):
        self.assertLess(release_check.parse_version("3.9.0"), release_check.parse_version("3.17.0"))
        self.assertLess(release_check.parse_version("3.17.0"), release_check.parse_version("3.18.0"))

    def test_ignores_drafts_prereleases_and_invalid_tags(self):
        releases = [
            {"tag_name": "v99.0.0", "draft": True, "prerelease": False, "html_url": "https://example.invalid/draft"},
            {"tag_name": "v98.0.0", "draft": False, "prerelease": True, "html_url": "https://example.invalid/pre"},
            {"tag_name": "v3.17.0; echo bad", "draft": False, "prerelease": False, "html_url": "https://example.invalid/injection"},
            {"tag_name": "v99.0.0", "html_url": "https://example.invalid/unmarked"},
            {"tag_name": "v3.18.0", "draft": False, "prerelease": False, "html_url": "https://example.invalid/v3.18.0"},
        ]
        result = release_check.build_status("3.17.0", releases)
        self.assertEqual(result["latest"], "3.18.0")
        self.assertEqual(
            result["releaseURL"],
            "https://github.com/410979729/scope-recall-hermes/releases/tag/v3.18.0",
        )
        self.assertTrue(result["update_available"])

    def test_never_offers_downgrade(self):
        result = release_check.build_status("3.18.0", [
            {"tag_name": "v3.17.0", "draft": False, "prerelease": False, "html_url": "https://example.invalid/v3.17.0"},
        ])
        self.assertFalse(result["update_available"])

    def test_release_link_preserves_tag_without_v_prefix(self):
        result = release_check.build_status("3.17.0", [
            {"tag_name": "3.18.0", "draft": False, "prerelease": False},
        ])
        self.assertEqual(result["latest"], "3.18.0")
        self.assertEqual(result["releaseURL"],
                         "https://github.com/410979729/scope-recall-hermes/releases/tag/3.18.0")

    def test_rejects_injected_current_version(self):
        with self.assertRaises(ValueError):
            release_check.parse_version("3.17.0; touch /tmp/pwned")

    def test_http_failure_is_not_reported_as_current(self):
        def fail(_request, timeout):
            raise OSError("offline")

        result = release_check.check("3.17.0", opener=fail)
        self.assertIsNone(result["latest"])
        self.assertIsNone(result["update_available"])
        self.assertEqual(result["error"], "release_check_failed")


if __name__ == "__main__":
    unittest.main()
