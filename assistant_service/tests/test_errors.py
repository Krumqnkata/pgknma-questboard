"""Кодовете на грешки от доставчиците стават ясни съобщения на български."""
import unittest

from providers.base import status_error


class ErrorMessageTests(unittest.TestCase):
    def message(self, code, detail=""):
        return str(status_error("Gemini", "gemini-3.8-flash", code, detail))

    def test_invalid_key(self):
        self.assertIn("Невалиден API ключ", self.message(401))
        self.assertIn("Невалиден API ключ", self.message(400, "API key not valid. Please pass a valid API key."))

    def test_no_access_is_not_called_invalid_key(self):
        self.assertIn("няма достъп до модела „gemini-3.8-flash“", self.message(403))

    def test_unknown_model(self):
        self.assertIn("не съществува", self.message(404))

    def test_overloaded_and_slow(self):
        self.assertIn("претоварен", self.message(503))
        self.assertIn("претоварен", self.message(529))
        self.assertIn("не отговори навреме", self.message(504))

    def test_detail_is_kept_for_the_admin(self):
        self.assertEqual(status_error("Gemini", "m", 503, "high demand").detail, "high demand")


if __name__ == "__main__":
    unittest.main()
