"""Silero VAD (Voice Activity Detection) Motoru — ONNX tabanlı, torch gerektirmez.

Düşük gecikmeli CPU tabanlı ses etkinliği tespiti. Asistan konuşurken
kullanıcı mikrofondan bir şey söylediği anda ses akışını susturur.
"""

from __future__ import annotations

from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)

try:
    import numpy as np
    import onnxruntime as ort

    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False


class VADEngine:
    """Silero VAD ONNX tabanlı ses etkinliği tespiti.

    Torch gerektirmez — doğrudan ONNX Runtime kullanarak PCM ses
    verisinde konuşma olup olmadığını tespit eder.
    """

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000) -> None:
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._session: Any = None
        self._h: Any = None
        self._c: Any = None
        self._initialized = False

    def initialize(self) -> bool:
        """Silero VAD ONNX modelini yükler. Kullanılabilirlik durumunu döndürür."""
        if not _ONNX_AVAILABLE:
            logger.warning("vad.onnx_not_available")
            return False

        try:
            import urllib.request
            from pathlib import Path

            model_dir = Path.home() / ".omnicore" / "models"
            model_dir.mkdir(parents=True, exist_ok=True)
            model_path = model_dir / "silero_vad.onnx"

            if not model_path.exists():
                url = (
                    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
                )
                logger.info("vad.downloading_model")
                urllib.request.urlretrieve(url, model_path)

            self._session = ort.InferenceSession(str(model_path))
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)
            self._initialized = True
            logger.info("vad.initialized")
            return True
        except Exception as exc:
            logger.warning("vad.init_failed", error=str(exc))
            return False

    def is_speech(self, audio_chunk: bytes) -> bool:
        """PCM 16-bit ses bloğunda konuşma olup olmadığını kontrol eder."""
        if not self._initialized or self._session is None:
            return False

        try:
            samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0

            if len(samples) == 0:
                return False

            if len(samples) < 512:
                samples = np.pad(samples, (0, 512 - len(samples)))

            audio_tensor = samples.reshape(1, -1)

            input_name = self._session.get_inputs()[0].name
            h_name = self._session.get_inputs()[1].name
            c_name = self._session.get_inputs()[2].name

            sr_tensor = np.array([self._sample_rate], dtype=np.int64)

            outputs = self._session.run(
                None,
                {
                    input_name: audio_tensor,
                    h_name: self._h,
                    c_name: self._c,
                    "sr": sr_tensor,
                },
            )

            self._h = outputs[1]
            self._c = outputs[2]
            probability = float(outputs[0][0])

            return probability > self._threshold
        except Exception:
            return False

    def reset(self) -> None:
        """Dahili durumu sıfırlar."""
        if self._initialized:
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)

    async def stream_listen(
        self,
        chunk_size: int = 512,
        max_duration: float | None = None,
    ):
        """Sürekli mikrofon akışını dinler ve konuşma tespit edilen blokları yield eder.

        Async generator olarak çalışır:
            async for speech_chunk in vad.stream_listen():
                ...
        """
        import asyncio

        import sounddevice as sd

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug("vad.stream_status", status=str(status))
            loop.call_soon_threadsafe(queue.put_nowait, indata.tobytes())

        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=chunk_size,
            callback=audio_callback,
        )

        with stream:
            start_time = loop.time()
            while True:
                if max_duration and (loop.time() - start_time) > max_duration:
                    break
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                if self.is_speech(chunk):
                    yield chunk
