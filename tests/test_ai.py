import unittest

from src.ai import detector, distance, speech


class AiModuleTests(unittest.TestCase):
    def test_ai_modules_are_importable(self):
        self.assertIsNotNone(detector)
        self.assertIsNotNone(distance)
        self.assertIsNotNone(speech)

    def test_safe_detection_has_a_spoken_message(self):
        message = speech.build_message(
            [
                {
                    "label": "person",
                    "distance_m": 4.2,
                    "direction": "ahead",
                    "danger_level": "safe",
                }
            ],
            language="en",
        )

        self.assertIn("person detected", message)
        self.assertIn("4.2 meters", message)

    def test_empty_detection_list_has_no_false_clear_message(self):
        self.assertIsNone(speech.build_message([], language="en"))


if __name__ == "__main__":
    unittest.main()
