from pathlib import Path
import unittest


class MobileUploadRegressionTest(unittest.TestCase):
    def test_file_list_is_snapshotted_before_file_input_is_reset(self):
        """Mobile browsers may clear the live FileList once input.value is reset."""
        source = Path(__file__).parents[1] / "static" / "index.html"
        script = source.read_text(encoding="utf-8")
        handler_start = script.index("input.addEventListener('change'")
        handler_end = script.index("  });", handler_start) + len("  });")
        handler = script[handler_start:handler_end]

        snapshot = "const files = Array.from(input.files);"
        reset = "input.value = '';"
        self.assertIn(snapshot, handler)
        self.assertIn(reset, handler)
        self.assertLess(handler.index(snapshot), handler.index(reset))


if __name__ == "__main__":
    unittest.main()
