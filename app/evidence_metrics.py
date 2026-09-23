import re
from difflib import SequenceMatcher

from .models import AssessmentRecord, LocalVideoEvidenceSummary


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
PASSAGE_START_MARKERS = (
    "read aloud article:",
    "article:",
)
PASSAGE_END_MARKERS = (
    "15 tough words",
    "10 simple sentences",
    "assessment boundary",
)
FLUENCY_VERSION = "provisional_v1"
FLUENCY_WEIGHTS = {
    "passage_continuity": 0.30,
    "pace_consistency": 0.25,
    "pause_continuity": 0.20,
    "restarts": 0.15,
    "task_pace": 0.10,
}


def normalized_words(value: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_PATTERN.finditer(value)]


def extract_expected_passage(module_content: str) -> str:
    value = module_content.strip()
    lowered = value.lower()
    start = 0
    for marker in PASSAGE_START_MARKERS:
        marker_index = lowered.find(marker)
        if marker_index >= 0:
            line_end = value.find("\n", marker_index)
            start = line_end + 1 if line_end >= 0 else marker_index + len(marker)
            break

    end = len(value)
    lowered_after_start = lowered[start:]
    for marker in PASSAGE_END_MARKERS:
        marker_index = lowered_after_start.find(marker)
        if marker_index >= 0:
            end = min(end, start + marker_index)

    candidate_lines = []
    for line in value[start:end].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        devanagari_count = sum("\u0900" <= character <= "\u097f" for character in stripped)
        if devanagari_count / max(len(stripped), 1) > 0.2:
            break
        candidate_lines.append(stripped)
    return " ".join(candidate_lines)


def passage_completion_metrics(
    transcript: str,
    module_content: str,
) -> tuple[int, int, float]:
    expected = normalized_words(extract_expected_passage(module_content))
    observed = normalized_words(transcript)
    if not expected or not observed:
        return 0, len(expected), 0.0

    previous = list(range(len(observed) + 1))
    matched_rows: list[list[int]] = [[0] * (len(observed) + 1)]
    for expected_word in expected:
        current = [previous[0] + 1]
        matched_current = [0]
        for column, observed_word in enumerate(observed, 1):
            similarity = SequenceMatcher(None, expected_word, observed_word).ratio()
            is_match = similarity >= 0.76
            substitution_cost = 0 if is_match else 1
            options = (
                (previous[column] + 1, matched_rows[-1][column]),
                (current[column - 1] + 1, matched_current[column - 1]),
                (
                    previous[column - 1] + substitution_cost,
                    matched_rows[-1][column - 1] + int(is_match),
                ),
            )
            best_cost, best_matches = min(options, key=lambda item: (item[0], -item[1]))
            current.append(best_cost)
            matched_current.append(best_matches)
        previous = current
        matched_rows.append(matched_current)

    matched = matched_rows[-1][-1]
    percentage = round(min(matched / len(expected) * 100, 100.0), 1)
    return matched, len(expected), percentage


def _target_wpm_range(grade_level: str, learner_type: str) -> tuple[float, float]:
    if learner_type == "adult_trainee":
        return 80.0, 160.0
    lowered = grade_level.lower()
    if any(value in lowered for value in ("pre-primary", "kindergarten", "kg")):
        return 20.0, 80.0
    match = re.search(r"\b(?:grade|class)?\s*(\d{1,2})\b", lowered)
    grade = int(match.group(1)) if match else 0
    if grade <= 0:
        return 40.0, 160.0
    if grade <= 2:
        return 30.0, 100.0
    if grade <= 5:
        return 50.0, 130.0
    if grade <= 8:
        return 70.0, 150.0
    return 80.0, 170.0


def _task_pace_score(
    active_wpm: float,
    target_min: float,
    target_max: float,
) -> float:
    if target_min <= active_wpm <= target_max:
        return 100.0
    distance = target_min - active_wpm if active_wpm < target_min else active_wpm - target_max
    return round(max(0.0, 100.0 - distance * 2), 1)


def apply_inferred_fluency_metrics(
    evidence: LocalVideoEvidenceSummary,
    grade_level: str,
    learner_type: str,
) -> None:
    evidence.inferred_fluency_version = FLUENCY_VERSION
    if evidence.evidence_quality == "insufficient":
        evidence.inferred_fluency_level = "insufficient_evidence"
        evidence.inferred_fluency_confidence = "none"
        return
    if evidence.passage_words_expected < 20 or evidence.active_speech_seconds <= 0:
        evidence.inferred_fluency_level = "not_available"
        evidence.inferred_fluency_confidence = "none"
        return

    word_count = max(evidence.transcript_word_count, 1)
    passage_continuity = round(
        evidence.passage_completion_percentage * 0.8
        + min(evidence.speech_ratio / 0.8, 1.0) * 100 * 0.2,
        1,
    )
    pause_rate = evidence.pause_count / word_count * 100
    long_pause_rate = evidence.long_pause_count / word_count * 100
    pause_continuity = round(
        max(0.0, 100.0 - pause_rate * 4 - long_pause_rate * 12),
        1,
    )
    restart_rate = evidence.possible_restart_count / word_count * 100
    restart_score = round(max(0.0, 100.0 - restart_rate * 12), 1)
    target_min, target_max = _target_wpm_range(grade_level, learner_type)
    task_pace = _task_pace_score(
        evidence.active_speech_wpm,
        target_min,
        target_max,
    )

    evidence.fluency_passage_continuity_score = passage_continuity
    evidence.fluency_pace_consistency_score = evidence.pace_consistency_score
    evidence.fluency_pause_continuity_score = pause_continuity
    evidence.fluency_restart_score = restart_score
    evidence.fluency_task_pace_score = task_pace
    evidence.fluency_target_wpm_min = target_min
    evidence.fluency_target_wpm_max = target_max
    evidence.inferred_fluency_score = round(
        passage_continuity * FLUENCY_WEIGHTS["passage_continuity"]
        + evidence.pace_consistency_score * FLUENCY_WEIGHTS["pace_consistency"]
        + pause_continuity * FLUENCY_WEIGHTS["pause_continuity"]
        + restart_score * FLUENCY_WEIGHTS["restarts"]
        + task_pace * FLUENCY_WEIGHTS["task_pace"],
        1,
    )
    if evidence.inferred_fluency_score >= 85:
        evidence.inferred_fluency_level = "strong"
    elif evidence.inferred_fluency_score >= 70:
        evidence.inferred_fluency_level = "consistent"
    elif evidence.inferred_fluency_score >= 50:
        evidence.inferred_fluency_level = "developing"
    else:
        evidence.inferred_fluency_level = "emerging"
    evidence.inferred_fluency_confidence = (
        "low" if evidence.evidence_quality == "review_recommended" else "moderate"
    )


def apply_video_assignment_metrics(
    evidence: LocalVideoEvidenceSummary,
    transcript: str,
    module_content: str,
    previous_records: list[AssessmentRecord],
    student_id: str,
    homework_id: str,
    grade_level: str = "",
    learner_type: str = "minor",
) -> None:
    matched, expected, completion = passage_completion_metrics(
        transcript,
        module_content,
    )
    evidence.passage_words_matched = matched
    evidence.passage_words_expected = expected
    evidence.passage_completion_percentage = completion
    apply_inferred_fluency_metrics(evidence, grade_level, learner_type)

    previous_evidence = next(
        (
            record.input.local_video_evidence
            for record in previous_records
            if record.input.student_id == student_id
            and record.input.homework_id == homework_id
            and record.input.local_video_evidence is not None
        ),
        None,
    )
    if previous_evidence is not None and previous_evidence.active_speech_seconds > 0:
        evidence.previous_active_speech_wpm = previous_evidence.active_speech_wpm
        evidence.active_speech_wpm_change = round(
            evidence.active_speech_wpm - evidence.previous_active_speech_wpm,
            1,
        )
    if (
        previous_evidence is not None
        and previous_evidence.passage_words_expected > 0
    ):
        evidence.previous_completion_percentage = (
            previous_evidence.passage_completion_percentage
        )
        evidence.completion_percentage_change = round(
            completion - evidence.previous_completion_percentage,
            1,
        )

    priority_flags = list(evidence.teacher_priority_flags)
    if evidence.evidence_quality != "good":
        priority_flags.append("Evidence quality needs teacher review.")
    if expected and completion < 70:
        priority_flags.append(
            "Passage completion is below 70%; check whether the learner needs support."
        )
    if evidence.long_pause_count >= 5:
        priority_flags.append(
            "Several long pauses were detected; review the transcript and recording context."
        )
    if evidence.possible_restart_count >= 5:
        priority_flags.append(
            "Repeated words or restarts were detected; confirm before giving guidance."
        )
    if (
        evidence.inferred_fluency_score is not None
        and evidence.inferred_fluency_score < 70
    ):
        priority_flags.append(
            "Provisional inferred fluency needs teacher confirmation and support review."
        )
    evidence.teacher_priority_flags = list(dict.fromkeys(priority_flags))
