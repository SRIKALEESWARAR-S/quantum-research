import unittest
import fetch

class RecordTests(unittest.TestCase):
    def test_gdelt_date_is_normalized(self):
        item = fetch.record("A useful science article", "https://example.org/a", "summary", "Example", "news", "20261024T123456Z")
        self.assertEqual(item["date"], "2026-10-24")

    def test_crossref_partial_date_is_normalized(self):
        item = fetch.record("A useful science article", "https://example.org/a", "summary", "Example", "research", "2024-03")
        self.assertEqual(item["date"], "2024-03-01")

    def test_invalid_urls_are_rejected(self):
        self.assertIsNone(fetch.record("A useful science article", "javascript:alert(1)", "summary", "Example", "news"))

    def test_missing_date_falls_back_to_today(self):
        item = fetch.record("A useful science article", "https://example.org/a", "summary", "Example", "research", "")
        self.assertEqual(item["date"], fetch.TODAY)

if __name__ == "__main__":
    unittest.main()
