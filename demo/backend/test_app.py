import base64
import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from demo.backend import app as app_module


def make_wav(frame_count: int, sample_value: int = 0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        frame = int(sample_value).to_bytes(2, byteorder="little", signed=True)
        wav_file.writeframes(frame * frame_count)
    return output.getvalue()


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class MiMoTTSTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audio_dir_patch = patch.object(app_module, "AUDIO_DIR", Path(self.temp_dir.name))
        self.audio_dir_patch.start()

    def tearDown(self):
        self.audio_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_mimo_adapter_uses_public_chat_completions_contract(self):
        wav_bytes = make_wav(32, 1)
        response = FakeResponse({
            "choices": [{"message": {"audio": {"data": base64.b64encode(wav_bytes).decode()}}}],
        })
        with (
            patch.object(app_module, "MIMO_TTS_API_KEY", "test-key"),
            patch.object(app_module, "MIMO_TTS_BASE_URL", "https://api.xiaomimimo.com/v1/"),
            patch.object(app_module.requests, "post", return_value=response) as post,
        ):
            result = app_module._generate_tts_chunk("愿你今晚睡个好觉")

        self.assertEqual(result, wav_bytes)
        request = post.call_args
        self.assertEqual(request.args[0], "https://api.xiaomimimo.com/v1/chat/completions")
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(request.kwargs["json"]["model"], app_module.MIMO_TTS_MODEL)
        self.assertEqual(request.kwargs["json"]["messages"][-1]["content"], "愿你今晚睡个好觉")
        self.assertEqual(request.kwargs["json"]["audio"], {"voice": app_module.MIMO_TTS_VOICE, "format": "wav"})

    def test_generate_tts_writes_single_chunk_as_local_wav(self):
        wav_bytes = make_wav(40, 2)
        with patch.object(app_module, "_generate_tts_chunk", return_value=wav_bytes) as synthesize:
            audio_url = app_module.generate_tts("一小段文字")

        synthesize.assert_called_once_with("一小段文字")
        self.assertRegex(audio_url, r"^/api/audio/[0-9a-f]{32}\.wav$")
        output_file = Path(self.temp_dir.name) / Path(audio_url).name
        self.assertEqual(output_file.read_bytes(), wav_bytes)

    def test_generate_tts_merges_long_text_chunks_without_ffmpeg(self):
        first = make_wav(25, 3)
        second = make_wav(35, 4)
        text = "甲" * 4500 + "。乙"
        with patch.object(app_module, "_generate_tts_chunk", side_effect=[first, second]) as synthesize:
            audio_url = app_module.generate_tts(text)

        self.assertEqual(synthesize.call_count, 2)
        output_file = Path(self.temp_dir.name) / Path(audio_url).name
        with wave.open(str(output_file), "rb") as wav_file:
            self.assertEqual(wav_file.getnframes(), 60)
            self.assertEqual(wav_file.getframerate(), 16000)

    def test_invalid_mimo_audio_fails_without_writing_a_file(self):
        response = FakeResponse({
            "choices": [{"message": {"audio": {"data": base64.b64encode(b"not-a-wav").decode()}}}],
        })
        with (
            patch.object(app_module, "MIMO_TTS_API_KEY", "test-key"),
            patch.object(app_module.requests, "post", return_value=response),
        ):
            self.assertIsNone(app_module._generate_tts_chunk("测试"))
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [])


class UpstreamIntegrationRegressionTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        app_module.TTS_JOBS.clear()

    def tearDown(self):
        app_module.TTS_JOBS.clear()

    def test_status_reports_mimo_and_upstream_image_capability(self):
        with (
            patch.object(app_module, "MIMO_TTS_API_KEY", "test-key"),
            patch.object(app_module, "IMAGE_API_KEY", "image-key"),
        ):
            payload = self.client.get("/api/status").get_json()

        self.assertTrue(payload["has_tts"])
        self.assertTrue(payload["has_image_generation"])

    def test_doodle_data_url_keeps_upstream_processing_flow(self):
        encoded = base64.b64encode(b"fake-image-bytes").decode()
        with (
            patch.object(app_module, "process_image", return_value="涂鸦叙事") as process_image,
            patch.object(app_module, "save_uploaded_photo", return_value="/api/images/doodle.jpg"),
            patch.object(app_module, "generate_tts", return_value="/api/audio/doodle.wav"),
            patch.object(app_module, "append_diary_record") as append_record,
            patch.object(app_module, "IMAGE_API_KEY", ""),
        ):
            response = self.client.post("/api/echo/generate", json={
                "type": "doodle",
                "content": f"data:image/png;base64,{encoded}",
                "theme": "测试主题",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["audio_url"], "/api/audio/doodle.wav")
        process_image.assert_called_once_with(b"fake-image-bytes", "doodle")
        self.assertEqual(append_record.call_args.args[1]["image_status"], "original")

    def test_long_text_still_uses_upstream_background_job(self):
        thread = Mock()
        with patch.object(app_module.threading, "Thread", return_value=thread) as thread_factory:
            response = self.client.post("/api/echo/generate", json={
                "type": "text",
                "content": "长" * 301,
                "theme": "测试主题",
            })

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertTrue(payload["pending"])
        self.assertEqual(app_module.TTS_JOBS[payload["job_id"]], {"status": "processing"})
        thread_factory.assert_called_once()
        thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
