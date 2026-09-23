from app.evidence_metrics import (
    apply_inferred_fluency_metrics,
    apply_video_assignment_metrics,
    extract_expected_passage,
    passage_completion_metrics,
)
from app.models import LocalVideoEvidenceSummary
from app.models import AssessmentCreate, AssessmentRecord, AssessmentResult
from app.transcription import (
    _evidence_quality,
    _pace_consistency,
    _possible_restart_count,
)


MODULE_CONTENT = """READ ALOUD ARTICLE: Delegating Tasks

Teachers can share simple classroom responsibilities with students.
Fair delegation builds confidence, teamwork, and shared leadership.

15 TOUGH WORDS AND HINDI MEANINGS
1. Delegation - कार्य सौंपना

10 SIMPLE SENTENCES
1. Share responsibilities fairly.
"""


def test_expected_passage_excludes_supplementary_lists():
    passage = extract_expected_passage(MODULE_CONTENT)

    assert "Teachers can share" in passage
    assert "15 TOUGH WORDS" not in passage
    assert "Share responsibilities fairly" not in passage


def test_passage_completion_is_deterministic_and_tolerates_small_word_errors():
    matched, expected, percentage = passage_completion_metrics(
        "Teachers can share classroom responsibilities with students. "
        "Fair delegation builds confidence teamwork and shared leadership.",
        MODULE_CONTENT,
    )

    assert expected == 16
    assert matched >= 14
    assert percentage >= 87


def test_video_assignment_metrics_add_priority_and_progress():
    evidence = LocalVideoEvidenceSummary(
        duration_seconds=100,
        transcript_word_count=12,
        estimated_words_per_minute=7.2,
        active_speech_seconds=60,
        active_speech_wpm=12,
        speech_ratio=0.6,
        pause_count=8,
        long_pause_count=5,
        longest_pause_seconds=4,
        possible_restart_count=5,
        low_confidence_segment_count=0,
        evidence_quality="good",
    )

    apply_video_assignment_metrics(
        evidence,
        "Teachers can share responsibilities.",
        MODULE_CONTENT,
        [],
        "student-1",
        "homework-1",
    )

    assert evidence.passage_words_expected == 16
    assert evidence.passage_completion_percentage < 70
    assert len(evidence.teacher_priority_flags) == 3


def test_legacy_overall_wpm_is_not_treated_as_active_speech_progress():
    evidence = LocalVideoEvidenceSummary(
        duration_seconds=100,
        transcript_word_count=100,
        estimated_words_per_minute=60,
        active_speech_seconds=80,
        active_speech_wpm=75,
        evidence_quality="good",
    )
    previous = AssessmentRecord(
        id="old-assessment",
        created_at="2026-01-01T00:00:00Z",
        status="approved",
        review_required=False,
        audit_trail=[],
        input=AssessmentCreate(
            homework_id="homework-1",
            student_id="student-1",
            student_name="Student",
            assignment_title="Assignment",
            assignment_prompt="Prompt",
            submission="Previous transcript",
            submission_type="video_and_handnote",
            permission_confirmed=True,
            external_media_processing_confirmed=True,
            media_processing_reference="LOCAL-VIDEO-old",
            local_video_evidence=LocalVideoEvidenceSummary(
                duration_seconds=100,
                transcript_word_count=100,
                estimated_words_per_minute=60,
            ),
            rubric=[
                {
                    "name": "Coverage",
                    "description": "Coverage",
                    "max_points": 100,
                }
            ],
        ),
        result=AssessmentResult(
            criterion_evaluations=[],
            total_score=0,
            max_score=100,
            percentage=0,
            strengths=[],
            learning_gaps=[],
            personalized_feedback="",
            recommendations=[],
            confidence={"score": 0.5, "rationale": "Legacy record"},
        ),
    )

    apply_video_assignment_metrics(
        evidence,
        "Teachers can share responsibilities.",
        MODULE_CONTENT,
        [previous],
        "student-1",
        "homework-1",
    )

    assert evidence.previous_active_speech_wpm is None
    assert evidence.active_speech_wpm_change is None
    assert evidence.previous_completion_percentage is None
    assert evidence.completion_percentage_change is None


def test_transcription_quality_and_restart_signals_are_objective():
    quality, flags = _evidence_quality(
        word_count=80,
        duration=100,
        active_speech_seconds=30,
        low_confidence_segment_count=4,
        segment_count=10,
    )

    assert quality == "review_recommended"
    assert len(flags) == 2
    assert _possible_restart_count("we can can try again try again") >= 2


def test_provisional_fluency_uses_published_component_weights():
    evidence = LocalVideoEvidenceSummary(
        duration_seconds=75,
        transcript_word_count=100,
        estimated_words_per_minute=80,
        active_speech_seconds=60,
        active_speech_wpm=100,
        speech_ratio=0.8,
        pause_count=2,
        long_pause_count=0,
        possible_restart_count=2,
        pace_consistency_score=80,
        passage_words_matched=90,
        passage_words_expected=100,
        passage_completion_percentage=90,
        evidence_quality="good",
    )

    apply_inferred_fluency_metrics(evidence, "Sample Test", "adult_trainee")

    assert evidence.fluency_passage_continuity_score == 92
    assert evidence.fluency_pause_continuity_score == 92
    assert evidence.fluency_restart_score == 76
    assert evidence.fluency_task_pace_score == 100
    assert evidence.inferred_fluency_score == 87.4
    assert evidence.inferred_fluency_level == "strong"
    assert evidence.inferred_fluency_confidence == "moderate"


def test_pace_consistency_reports_variability_without_audio_traits():
    score, variability = _pace_consistency(
        [
            {"start_seconds": 0, "end_seconds": 10, "text": "one two three four five"},
            {"start_seconds": 10, "end_seconds": 20, "text": "six seven eight nine ten"},
        ]
    )

    assert score == 100
    assert variability == 0
