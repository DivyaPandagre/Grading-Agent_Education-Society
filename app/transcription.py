import os
import re
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev


class LocalTranscriptionError(RuntimeError):
    pass


def _possible_restart_count(transcript: str) -> int:
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", transcript.lower())
    repeated_words = sum(
        1 for previous, current in zip(words, words[1:]) if previous == current
    )
    repeated_phrases = 0
    for size in (2, 3):
        for index in range(size, len(words) - size + 1):
            if words[index - size:index] == words[index:index + size]:
                repeated_phrases += 1
    return repeated_words + repeated_phrases


def _evidence_quality(
    word_count: int,
    duration: float,
    active_speech_seconds: float,
    low_confidence_segment_count: int,
    segment_count: int,
) -> tuple[str, list[str]]:
    flags = []
    speech_ratio = active_speech_seconds / duration if duration else 0
    low_confidence_ratio = (
        low_confidence_segment_count / segment_count if segment_count else 1
    )
    if word_count < 10:
        flags.append("Too little speech was transcribed for reliable assessment.")
    if speech_ratio < 0.2:
        flags.append("Speech was detected in less than 20% of the recording.")
    elif speech_ratio < 0.45:
        flags.append("A large portion of the recording did not contain detected speech.")
    if low_confidence_ratio > 0.35:
        flags.append("More than 35% of transcript segments had low recognition confidence.")

    if word_count < 10 or speech_ratio < 0.2:
        return "insufficient", flags
    if flags:
        return "review_recommended", flags
    return "good", flags


def _pace_consistency(segments: list[dict]) -> tuple[float, float]:
    segment_paces = []
    for segment in segments:
        duration = segment["end_seconds"] - segment["start_seconds"]
        word_count = len(segment["text"].split())
        if duration >= 1 and word_count >= 3:
            segment_paces.append(word_count / (duration / 60))
    if len(segment_paces) < 2:
        return 0.0, 0.0
    average_pace = mean(segment_paces)
    if average_pace <= 0:
        return 0.0, 0.0
    variability = pstdev(segment_paces) / average_pace * 100
    score = max(0.0, 100.0 - variability)
    return round(score, 1), round(variability, 1)


@lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise LocalTranscriptionError(
            "Local transcription is not installed. Install project requirements."
        ) from exc

    model_name = os.getenv("LOCAL_WHISPER_MODEL", "small")
    try:
        return WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as exc:
        raise LocalTranscriptionError(
            f'Local Whisper model "{model_name}" could not be loaded: {exc}'
        ) from exc


def transcribe_local_video(path: Path) -> dict:
    try:
        segments, info = _model().transcribe(
            str(path),
            beam_size=5,
            vad_filter=True,
        )
        collected = []
        transcript_parts = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            transcript_parts.append(text)
            collected.append(
                {
                    "start_seconds": round(float(segment.start), 1),
                    "end_seconds": round(float(segment.end), 1),
                    "text": text,
                    "avg_log_probability": round(
                        float(getattr(segment, "avg_logprob", 0) or 0),
                        3,
                    ),
                    "no_speech_probability": round(
                        float(getattr(segment, "no_speech_prob", 0) or 0),
                        3,
                    ),
                }
            )
        transcript = " ".join(transcript_parts).strip()
        if not transcript:
            raise LocalTranscriptionError(
                "No academic speech could be transcribed from the video."
            )
        duration = max(
            [float(item["end_seconds"]) for item in collected],
            default=float(getattr(info, "duration", 0) or 0),
        )
        word_count = len(transcript.split())
        active_speech_seconds = round(
            sum(
                max(0.0, float(item["end_seconds"]) - float(item["start_seconds"]))
                for item in collected
            ),
            1,
        )
        gaps = [
            round(
                max(
                    0.0,
                    float(current["start_seconds"]) - float(previous["end_seconds"]),
                ),
                1,
            )
            for previous, current in zip(collected, collected[1:])
        ]
        pauses = [gap for gap in gaps if gap >= 0.6]
        long_pauses = [gap for gap in gaps if gap >= 2.0]
        low_confidence_segment_count = sum(
            1
            for item in collected
            if item["avg_log_probability"] < -1.0
            or item["no_speech_probability"] > 0.6
        )
        evidence_quality, quality_flags = _evidence_quality(
            word_count,
            duration,
            active_speech_seconds,
            low_confidence_segment_count,
            len(collected),
        )
        pace_consistency_score, pace_variability_percentage = _pace_consistency(
            collected
        )
        return {
            "transcript": transcript,
            "language": getattr(info, "language", "") or "",
            "duration_seconds": round(duration, 1),
            "word_count": word_count,
            "estimated_words_per_minute": round(
                word_count / (duration / 60), 1
            )
            if duration
            else 0,
            "active_speech_seconds": active_speech_seconds,
            "active_speech_wpm": round(
                word_count / (active_speech_seconds / 60),
                1,
            )
            if active_speech_seconds
            else 0,
            "speech_ratio": round(
                active_speech_seconds / duration,
                3,
            )
            if duration
            else 0,
            "pause_count": len(pauses),
            "long_pause_count": len(long_pauses),
            "longest_pause_seconds": max(pauses, default=0),
            "possible_restart_count": _possible_restart_count(transcript),
            "low_confidence_segment_count": low_confidence_segment_count,
            "pace_consistency_score": pace_consistency_score,
            "pace_variability_percentage": pace_variability_percentage,
            "evidence_quality": evidence_quality,
            "quality_flags": quality_flags,
            "segments": collected,
        }
    except LocalTranscriptionError:
        raise
    except Exception as exc:
        raise LocalTranscriptionError(
            f"Local video transcription failed: {exc}"
        ) from exc
