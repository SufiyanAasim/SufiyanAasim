import unittest

from scripts.generate_language_card import (
    eligible_repositories,
    render_svg,
    summarize_languages,
)


class EligibleRepositoriesTests(unittest.TestCase):
    def test_excludes_profile_forks_archived_private_and_missing_language_url(self):
        repositories = [
            {"name": "SufiyanAasim", "languages_url": "profile"},
            {"name": "fork", "fork": True, "languages_url": "fork"},
            {"name": "archive", "archived": True, "languages_url": "archive"},
            {"name": "private", "private": True, "languages_url": "private"},
            {"name": "empty"},
            {"name": "active", "languages_url": "active"},
        ]

        included = eligible_repositories(repositories, "SufiyanAasim")

        self.assertEqual([repository["name"] for repository in included], ["active"])


class LanguageSummaryTests(unittest.TestCase):
    def test_top_five_and_other_are_truthful_shares_of_all_bytes(self):
        totals = {
            "Python": 310,
            "JavaScript": 290,
            "C#": 180,
            "Jupyter Notebook": 60,
            "HTML": 40,
            "Java": 30,
            "Shell": 20,
        }

        summary = summarize_languages(totals, repository_count=12)

        self.assertEqual(
            [row["name"] for row in summary["languages"]],
            ["Python", "JavaScript", "C#", "Jupyter Notebook", "HTML", "Other"],
        )
        self.assertEqual(summary["languages"][-1]["bytes"], 50)
        self.assertAlmostEqual(
            sum(row["percent"] for row in summary["languages"]), 100.0, places=1
        )

    def test_empty_totals_fail_instead_of_publishing_empty_artifact(self):
        with self.assertRaises(RuntimeError):
            summarize_languages({}, repository_count=0)

    def test_svg_is_accessible_animated_and_reduced_motion_safe(self):
        summary = summarize_languages(
            {"Python": 60, "JavaScript": 30, "C#": 10}, repository_count=3
        )

        svg = render_svg("SufiyanAasim", summary)

        self.assertIn("aria-labelledby=\"title desc\"", svg)
        self.assertIn("MOST USED LANGUAGES", svg)
        self.assertIn("prefers-reduced-motion:reduce", svg)
        self.assertIn("Other", svg)


if __name__ == "__main__":
    unittest.main()
