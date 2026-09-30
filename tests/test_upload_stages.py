from __future__ import annotations

import unittest

try:  # The lifecycle helpers live next to the FastAPI router and its RAG imports.
    from upload import _get_task, _set_task
except ModuleNotFoundError:  # pragma: no cover - exercised only without backend deps
    _set_task = None


@unittest.skipIf(_set_task is None, "backend dependencies (fastapi/langchain) are not installed")
class UploadStageTimestampTests(unittest.TestCase):
    def test_every_stage_records_its_first_timestamp(self) -> None:
        upload_id = "upload_fixture"
        _set_task(upload_id, status="queued", stage="queued", stage_label="等待索引")
        _set_task(upload_id, status="processing", stage="parsing", stage_index=1)
        _set_task(upload_id, status="processing", stage="chunking", stage_index=2)
        _set_task(upload_id, stage="chunking", stage_index=2)
        _set_task(upload_id, status="completed", stage="ready", stage_index=5)

        task = _get_task(upload_id)
        self.assertIsNotNone(task)
        timestamps = task["stage_timestamps"]
        self.assertEqual(sorted(timestamps), ["chunking", "parsing", "queued", "ready"])
        self.assertTrue(all(isinstance(value, str) and value for value in timestamps.values()))
        self.assertLessEqual(timestamps["queued"], timestamps["ready"])


if __name__ == "__main__":
    unittest.main()
