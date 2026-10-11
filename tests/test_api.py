import asyncio
import io
from pathlib import Path
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from src.auth import get_current_user
from src.ai.detector import DetectorUnavailable
from src.main import (
    MAX_IMAGE_BYTES,
    app,
    battery_status,
    detect_objects,
    get_data,
    get_speech_audio,
    location_from_image,
    reverse_location,
)


class ApiTests(unittest.TestCase):
    def test_get_data_returns_message(self):
        result = asyncio.run(get_data())

        self.assertEqual(result, {"message": "Hello from FastAPI Backend!"})

    def test_battery_status_returns_monitor_status(self):
        monitor = MagicMock()
        monitor.get_status.return_value = {
            "available": True,
            "percent": 75,
            "plugged": False,
        }

        with patch("src.main.get_battery_monitor", return_value=monitor):
            result = battery_status(SimpleNamespace(id=7))

        self.assertEqual(result, monitor.get_status.return_value)

    def test_reverse_location_returns_address_and_coordinates(self):
        with patch("src.main.reverse_geocode", return_value="Example Street, Example City"):
            result = asyncio.run(
                reverse_location(12.3, 45.6, current_user=SimpleNamespace(id=7))
            )

        self.assertEqual(
            result,
            {
                "latitude": 12.3,
                "longitude": 45.6,
                "address": "Example Street, Example City",
                "description": "Your current location is Example Street, Example City.",
            },
        )

    def test_reverse_location_falls_back_to_coordinates_without_address(self):
        with patch("src.main.reverse_geocode", return_value=None):
            result = asyncio.run(
                reverse_location(12.3, 45.6, current_user=SimpleNamespace(id=7))
            )

        self.assertIsNone(result["address"])
        self.assertIn("latitude 12.3, longitude 45.6", result["description"])

    def test_reverse_geocode_uses_nominatim_and_selected_language(self):
        from src.accessibility.location import reverse_geocode

        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'{"display_name":"Merkato Market, Addis Ababa, Ethiopia"}'
        )

        with patch("src.accessibility.location.urlopen", return_value=response) as open_url:
            address = reverse_geocode(9.03, 38.74, "am-ET")

        self.assertEqual(address, "Merkato Market, Addis Ababa, Ethiopia")
        request = open_url.call_args.args[0]
        self.assertIn("nominatim.openstreetmap.org/reverse?", request.full_url)
        self.assertEqual(request.get_header("User-agent"), "AI-Obstacle-Detection/1.0 (assistive navigation app)")
        self.assertEqual(request.get_header("Accept-language"), "am-ET")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 8)

    def test_reverse_geocode_returns_none_on_provider_failure(self):
        from src.accessibility.location import reverse_geocode

        with patch(
            "src.accessibility.location.urlopen",
            side_effect=OSError("network unavailable"),
        ):
            self.assertIsNone(reverse_geocode(9.03, 38.74))

    def test_accessibility_endpoints_are_registered_and_authenticated(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
        gps = {"latitude": 12.3, "longitude": 45.6}
        monitor = MagicMock()
        monitor.get_status.return_value = {"available": True, "percent": 75, "plugged": False}

        try:
            with (
                TestClient(app) as client,
                patch("src.main.get_battery_monitor", return_value=monitor),
                patch("src.main.get_gps_from_image", return_value=gps),
                patch("src.main.describe_location", return_value="Your current location."),
                patch("src.main.reverse_geocode", return_value="Example Street, Example City"),
            ):
                battery_response = client.get("/api/battery")
                reverse_response = client.get(
                    "/api/location/reverse?latitude=12.3&longitude=45.6"
                )
                location_response = client.post(
                    "/api/location/from-image",
                    files={"image": ("frame.jpg", b"image bytes", "image/jpeg")},
                )

            self.assertEqual(battery_response.status_code, 200)
            self.assertEqual(battery_response.json(), monitor.get_status.return_value)
            self.assertEqual(reverse_response.status_code, 200)
            self.assertEqual(reverse_response.json()["address"], "Example Street, Example City")
            self.assertEqual(location_response.status_code, 200)
            self.assertEqual(
                location_response.json(),
                {**gps, "description": "Your current location."},
            )
        finally:
            app.dependency_overrides.clear()

    def test_location_endpoint_extracts_gps_and_cleans_up_temporary_file(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"image bytes"),
            headers={"content-type": "image/jpeg"},
        )
        gps = {"latitude": 12.3, "longitude": 45.6}

        with (
            patch("src.main.get_gps_from_image", return_value=gps) as get_gps,
            patch("src.main.describe_location", return_value="Your current location."),
        ):
            result = asyncio.run(location_from_image(image, SimpleNamespace(id=7)))

        self.assertEqual(
            result,
            {
                **gps,
                "description": "Your current location.",
            },
        )
        self.assertFalse(Path(get_gps.call_args.args[0]).exists())

    def test_location_endpoint_returns_404_when_image_has_no_gps(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"image bytes"),
            headers={"content-type": "image/jpeg"},
        )

        with (
            patch("src.main.get_gps_from_image", return_value=None),
            self.assertRaises(HTTPException) as raised,
        ):
            asyncio.run(location_from_image(image, SimpleNamespace(id=7)))

        self.assertEqual(raised.exception.status_code, 404)

    def test_location_endpoint_rejects_unsupported_image_type(self):
        image = UploadFile(
            filename="frame.txt",
            file=io.BytesIO(b"not an image"),
            headers={"content-type": "text/plain"},
        )

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(location_from_image(image, SimpleNamespace(id=7)))

        self.assertEqual(raised.exception.status_code, 415)

    def test_location_endpoint_rejects_oversized_image(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"x" * (MAX_IMAGE_BYTES + 1)),
            headers={"content-type": "image/jpeg"},
        )

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(location_from_image(image, SimpleNamespace(id=7)))

        self.assertEqual(raised.exception.status_code, 413)

    def test_tts_endpoint_returns_audio_from_google(self):
        upstream = MagicMock()
        upstream.__enter__.return_value = upstream
        upstream.headers.get_content_type.return_value = "audio/mpeg"
        upstream.read.return_value = b"ID3 audio"

        with patch("src.main.urlopen", return_value=upstream):
            result = get_speech_audio("ሰላም", "am", SimpleNamespace(id=7))

        self.assertEqual(result.media_type, "audio/mpeg")
        self.assertEqual(result.body, b"ID3 audio")
        self.assertEqual(result.headers["X-TTS-Provider"], "google")

    def test_local_tts_endpoint_returns_wav_for_local_languages(self):
        audio_data = b"RIFF\x00\x00\x00\x00WAVE"
        model_ids = {
            "ti": "facebook/mms-tts-tir",
            "om": "facebook/mms-tts-orm",
            "so": "facebook/mms-tts-som",
        }

        with patch("src.main.synthesize_local_tts", return_value=audio_data) as synthesize:
            for language, model_id in model_ids.items():
                with self.subTest(language=language):
                    result = get_speech_audio("sample", language, SimpleNamespace(id=7))

                    self.assertEqual(result.media_type, "audio/wav")
                    self.assertEqual(result.body, audio_data)
                    self.assertEqual(result.headers["X-TTS-Provider"], "local-mms")

        self.assertEqual(synthesize.call_count, 3)
        self.assertEqual(
            [call.args for call in synthesize.call_args_list],
            [("sample", model_id) for model_id in model_ids.values()],
        )

    def test_local_tts_endpoint_reports_model_failure(self):
        with (
            patch("src.main.synthesize_local_tts", side_effect=OSError("model unavailable")),
            self.assertRaises(HTTPException) as raised,
        ):
            get_speech_audio("Hello", "om", SimpleNamespace(id=7))

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("Local speech for 'om' is unavailable", raised.exception.detail)

    def test_google_tts_endpoint_reports_unsupported_language(self):
        rejected = HTTPError(
            "https://translate.google.com/translate_tts",
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )

        with (
            patch("src.main.urlopen", side_effect=rejected),
            self.assertRaises(HTTPException) as raised,
        ):
            get_speech_audio("Hello", "fa", SimpleNamespace(id=7))

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("does not support language 'fa'", raised.exception.detail)
        rejected.close()

    def test_tts_endpoint_rejects_non_audio_provider_response(self):
        upstream = MagicMock()
        upstream.__enter__.return_value = upstream
        upstream.headers.get_content_type.return_value = "text/html"
        upstream.read.return_value = b"<html>Bad Request</html>"

        with (
            patch("src.main.urlopen", return_value=upstream),
            self.assertRaises(HTTPException) as raised,
        ):
            get_speech_audio("Hello", "es", SimpleNamespace(id=7))

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("non-audio response", raised.exception.detail)

    def test_detect_endpoint_is_exposed_as_multipart_upload(self):
        operation = app.openapi()["paths"]["/api/detect"]["post"]

        self.assertIn("multipart/form-data", operation["requestBody"]["content"])

    def test_detect_endpoint_enriches_and_saves_frame_results(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"image bytes"),
            headers={"content-type": "image/jpeg"},
        )
        frame = SimpleNamespace(shape=(480, 640, 3))
        raw_detections = [
            {
                "label": "person",
                "confidence": 0.92,
                "bbox": [10, 0, 100, 480],
            }
        ]
        db = object()
        user = SimpleNamespace(id=7)

        with (
            patch("src.main.decode_image", return_value=frame),
            patch("src.main.detector.detect", return_value=raw_detections),
            patch("src.main.save_detections") as save,
        ):
            response = detect_objects(
                image,
                language="am",
                current_user=user,
                db=db,
            )

        self.assertEqual((response.width, response.height), (640, 480))
        self.assertEqual(response.count, 1)
        self.assertEqual(response.detections[0].direction, "left")
        self.assertEqual(response.detections[0].danger_level, "danger")
        self.assertIsNotNone(response.message)
        self.assertIn("ቁም!", response.message)
        self.assertIn("Stop!", response.fallback_message)
        saved_db, saved_user_id, saved_detections = save.call_args.args
        self.assertIs(saved_db, db)
        self.assertEqual(saved_user_id, user.id)
        self.assertEqual(saved_detections[0]["label"], "person")
        self.assertEqual(saved_detections[0]["danger_level"], "danger")

    def test_detect_endpoint_reports_unavailable_model_without_fake_results(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"image bytes"),
            headers={"content-type": "image/jpeg"},
        )
        db = object()
        user = SimpleNamespace(id=7)

        with (
            patch("src.main.decode_image", return_value=SimpleNamespace(shape=(10, 10, 3))),
            patch(
                "src.main.detector.detect",
                side_effect=DetectorUnavailable("YOLO model is unavailable."),
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            detect_objects(image, user, db)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "YOLO model is unavailable.")

    def test_detect_endpoint_rejects_oversized_upload(self):
        image = UploadFile(
            filename="frame.jpg",
            file=io.BytesIO(b"x" * (MAX_IMAGE_BYTES + 1)),
            headers={"content-type": "image/jpeg"},
        )

        with self.assertRaises(HTTPException) as raised:
            detect_objects(image, SimpleNamespace(id=7), object())

        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
