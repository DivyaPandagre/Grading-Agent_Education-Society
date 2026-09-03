"""The end-to-end grading run for one submission.

This is the only place the stages are wired together. Every external
dependency arrives as a constructor argument, so the same pipeline runs
offline with rule-based scorers or in production against real models and the
portal, with no change here.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from .feedback import build_feedback
from .models import (
    ArtifactKind,
    ArtifactResult,
    GradedSubmission,
    Module,
    Submission,
)
from .providers import (
    NoteEvidence,
    NoteScorer,
    VideoEvidence,
    VideoScorer,
    check_note,
    check_video,
)
from .rubric import Rubric
from .scoring import build_artifact_result, grade_submission
from .trend import compute_trend


class GradingPipeline:
    def __init__(
        self,
        rubric: Rubric,
        video_scorer: VideoScorer,
        note_scorer: NoteScorer,
        feedback_writer=None,
    ):
        self.rubric = rubric
        self.video_scorer = video_scorer
        self.note_scorer = note_scorer
        self.feedback_writer = feedback_writer

    def grade(
        self,
        submission: Submission,
        module: Module,
        video_evidence: Optional[VideoEvidence] = None,
        note_evidence: Optional[NoteEvidence] = None,
        previous_ratings: Sequence[float] = (),
    ) -> GradedSubmission:
        video = self._grade_video(video_evidence, module)
        note = self._grade_note(note_evidence, module)

        graded = grade_submission(
            submission_id=submission.submission_id,
            student_id=submission.student_id,
            module_id=module.module_id,
            video=video,
            note=note,
            rubric=self.rubric,
            previous_ratings=previous_ratings,
        )

        graded.trend = compute_trend(graded.overall_rating, previous_ratings, self.rubric)

        # A model-written note is preferred when available; the deterministic
        # builder is the fallback so a provider outage never leaves a student
        # with a score and no explanation.
        written = None
        if self.feedback_writer is not None:
            written = self.feedback_writer.write(graded, module)
        graded.feedback = written or build_feedback(graded, self.rubric, trend=graded.trend)

        graded.graded_at = date.today().isoformat()
        graded.extras["skill_type"] = module.skill_type
        return graded

    # -- per-artifact -----------------------------------------------------

    def _grade_video(self, evidence: Optional[VideoEvidence], module: Module) -> ArtifactResult:
        if evidence is None:
            return build_artifact_result(ArtifactKind.VIDEO, missing=True)

        blocker = check_video(evidence)
        if blocker is not None:
            return build_artifact_result(ArtifactKind.VIDEO, cannot_evaluate=blocker)

        return build_artifact_result(
            ArtifactKind.VIDEO, self.video_scorer.score(evidence, module))

    def _grade_note(self, evidence: Optional[NoteEvidence], module: Module) -> ArtifactResult:
        if evidence is None:
            return build_artifact_result(ArtifactKind.NOTE, missing=True)

        blocker = check_note(evidence)
        if blocker is not None:
            return build_artifact_result(ArtifactKind.NOTE, cannot_evaluate=blocker)

        return build_artifact_result(
            ArtifactKind.NOTE, self.note_scorer.score(evidence, module))
