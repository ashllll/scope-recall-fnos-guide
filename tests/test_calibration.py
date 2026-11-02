"""Exercise the calibration request without network, keys, or filesystem writes."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import types
import unittest
from unittest.mock import Mock, patch


class CalibrationTests(unittest.TestCase):
    def test_uses_upstream_document_query_encoding_and_cross_pairs(self):
        encoder = Mock(side_effect=lambda text, *, kind: f"{kind}:{text}")
        module = types.ModuleType("scope_recall.core.recall_policy")
        module.encode_embedding_text = encoder
        payloads = []
        reports = []

        def open_request(request, timeout):
            payloads.append(json.loads(request.data))
            rows = []
            for index in range(8):
                vector = [0.0] * 1536
                vector[index // 2] = 1.0
                rows.append({"index": index, "embedding": vector})
            return io.BytesIO(json.dumps({"model": "text-embedding-3-small", "data": rows, "usage": {}}).encode())

        original_read = Path.read_text

        def read(path, *args, **kwargs):
            if str(path) == "/config/model.env":
                return "OPENAI_API_KEY=YOUR_OPENAI_API_KEY\n"
            return original_read(path, *args, **kwargs)

        def write(path, text, *args, **kwargs):
            self.assertEqual(str(path), "/config/embedding-check.json")
            reports.append(json.loads(text))
            return len(text)

        script = Path(__file__).resolve().parents[1] / "deploy/calibrate.py"
        with patch.dict("sys.modules", {module.__name__: module}), \
             patch.object(Path, "read_text", read), \
             patch.object(Path, "write_text", write), \
             patch("urllib.request.urlopen", open_request), \
             contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(script), run_name="__main__")
        self.assertEqual([call.kwargs["kind"] for call in encoder.call_args_list],
                         ["document", "query"] * 4)
        self.assertEqual(len(payloads), 1)
        self.assertTrue(all(text.startswith(kind + ":") for text, kind in
                            zip(payloads[0]["input"], ["document", "query"] * 4)))
        self.assertEqual(len(reports[0]["positive_cosines"]), 4)
        self.assertEqual(len(reports[0]["negative_cosines"]), 12)
        self.assertEqual(reports[0]["vector_threshold"], 0.5)


if __name__ == "__main__":
    unittest.main()
