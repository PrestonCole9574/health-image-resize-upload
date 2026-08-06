import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from health_image_upload import InfraiStorage, prepare_renditions


class InfraiStorageTest(unittest.TestCase):
    @patch.object(InfraiStorage, "_json_request")
    def test_create_bucket_sends_required_name(self, request) -> None:
        InfraiStorage("test-key").create_bucket("images")

        request.assert_called_once_with(
            "POST", "/v1/storage/bucket/create", {"name": "images"}
        )


class PrepareRenditionsTest(unittest.TestCase):
    def test_caps_dimensions_and_uses_stable_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scan.png"
            Image.new("RGB", (2400, 1200), "white").save(source)

            first = prepare_renditions(source, "case 42")
            second = prepare_renditions(source, "case 42")

            self.assertEqual([item.key for item in first], [item.key for item in second])
            self.assertEqual((2048, 1024), (first[0].width, first[0].height))
            self.assertEqual((320, 160), (first[1].width, first[1].height))
            self.assertIn("patients/case%2042/", first[0].key)
            for item in first:
                with Image.open(io.BytesIO(item.data)) as image:
                    self.assertEqual("JPEG", image.format)


if __name__ == "__main__":
    unittest.main()
