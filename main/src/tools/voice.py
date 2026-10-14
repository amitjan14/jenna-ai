from main.src.utils import regex_constants as rx
import io
import math
import re
import threading
import wave
from kokoro import KPipeline
from functools import lru_cache
from faster_whisper import WhisperModel

import numpy as np
import torch


@lru_cache(maxsize=1)
def get_transcriber():
    # Lazy import: typed chat works without loading Whisper.

    model = WhisperModel(
        "base",
        device="cpu",
        compute_type="int8",
    )

    return model, threading.Lock()


def transcribe_audio(audio_bytes):
    if not audio_bytes:
        raise ValueError("Record a voice message first.")

    with wave.open(io.BytesIO(audio_bytes), "rb") as recording:
        rate = recording.getframerate()
        frames = recording.getnframes()

        if rate <= 0 or frames <= 0:
            raise ValueError("The recording contains no audio.")

        duration = frames / rate

        if not math.isfinite(duration) or duration > 60:
            raise ValueError("Please record a message of up to 60 seconds.")

    model, lock = get_transcriber()

    with lock:
        segments, _ = model.transcribe(
            io.BytesIO(audio_bytes),
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )

        transcript = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

    if not transcript:
        raise ValueError(
            "No speech was detected. Please record again."
        )

    return transcript


def prepare_speech_text(text):
    # Remove macOS speech-control sequences and Markdown formatting.
    text = re.sub(rx.SPEECH_CONTROL, "", text, flags=re.DOTALL)
    text = re.sub(rx.FENCED_CODE, "", text, flags=re.DOTALL)
    text = re.sub(rx.MARKDOWN_LINK, rx.MARKDOWN_LINK_REPLACEMENT, text)
    text = re.sub(rx.MARKDOWN_HEADING, "", text)
    text = text.replace("**", "").replace("`", "")
    text = text.strip()

    if len(text) > 2000:
        text = (
            text[:2000]
            + ". The remaining answer is available in the chat."
        )

    return text


_tts_lock = threading.Lock()

@lru_cache(maxsize=1)
def get_speech_pipeline():
    # Loaded only when a spoken reply is requested.

    return KPipeline(
        lang_code="b",
        repo_id="hexgrad/Kokoro-82M",
        device="cpu",
    )

def synthesize_speech(text):
    text = prepare_speech_text(text)

    if not text:
        raise ValueError("There is no readable text to speak.")

    chunks = []

    # Consume the generator while holding the lock.
    with _tts_lock, torch.inference_mode():
        pipeline = get_speech_pipeline()

        for _, _, audio in pipeline(
                text,
                voice="bf_alice",
                speed=0.88,
                split_pattern=rx.SPEECH_LINE_BREAK,
        ):
            if audio is None:
                continue

            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()

            samples = np.asarray(audio, dtype=np.float32)

            if samples.ndim != 1:
                raise RuntimeError(
                    "Kokoro returned an unexpected audio shape."
                )

            if not samples.size:
                continue

            if not np.isfinite(samples).all():
                raise RuntimeError(
                    "Kokoro returned invalid audio samples."
                )

            chunks.append(samples)

    if not chunks:
        raise RuntimeError("Kokoro returned no speech audio.")

    audio = np.concatenate(chunks)

    if np.max(np.abs(audio)) < 1e-8:
        raise RuntimeError("Kokoro returned silent audio.")

    pcm = (
            np.clip(audio, -1.0, 1.0) * 32767
    ).astype("<i2")

    output = io.BytesIO()

    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(24000)
        recording.writeframes(pcm.tobytes())

    return output.getvalue()
