# Homework Grading Agent

Grading agent for **Wazir Education Society**. Built to the design in
[`wiki/Homework-Grading-Agent.md`](../wiki/Homework-Grading-Agent.md).

A student submits a video of themselves reading from a module, plus a handwritten
note. The agent produces three ratings — video, note, and an overall — and one short
bilingual feedback note, automatically, with no manual step required from the teacher.

## Status

First milestone: **the scoring core, fully tested.** Everything that does not need a
model call is implemented and covered by tests. Model-dependent scoring (real ASR,
vision) sits behind interfaces with deterministic stand-ins, so the pipeline runs end
to end today without an API key.

Nothing here should grade real students until it has been calibrated against a teacher
marking the same submissions by hand. See *Before this grades anyone* below.

## Quick start

```bash
python -m unittest discover -s tests    # 57 tests, no dependencies
python build_notebook.py                # regenerate the walkthrough notebook
```

```python
from grading_agent import (
    GradingPipeline, Rubric, Module, Submission,
    RuleBasedVideoScorer, RuleBasedNoteScorer, VideoEvidence, NoteEvidence,
)

pipeline = GradingPipeline(Rubric.load(), RuleBasedVideoScorer(), RuleBasedNoteScorer())
graded = pipeline.grade(submission, module, video_evidence, note_evidence)

print(graded.video.rating, graded.note.rating, graded.overall_rating)
print(graded.feedback.en)
print(graded.feedback.hi)
```

`Grading_Agent_Walkthrough.ipynb` runs the whole thing with real captured output.

## Layout

| File | What it holds |
|---|---|
| `models.py` | Core types. Enforces two design rules structurally: a missing score cannot be represented as zero, and "cannot evaluate" is an outcome rather than an exception |
| `rubric_config.json` | The rubric — parameters, thresholds, weights. Calibration changes numbers here, not code |
| `rubric.py` | Config loading and lookup |
| `scoring.py` | Parameter scores → video / note / overall ratings, and teacher flags |
| `devanagari.py` | Answer-key matching for the handwritten Hindi |
| `trend.py` | Baseline / Improved / Stable / Needs attention |
| `feedback.py` | Bilingual feedback assembly |
| `providers.py` | The pluggable seams, plus rule-based reference scorers |
| `pipeline.py` | The one place the stages are wired together |
| `store.py` | Graded-submission records and rating history |

## Design rules the tests actually enforce

These are the tests worth keeping if the code is ever refactored, because each one
protects a student from a specific way an automated grader can do harm.

| Rule | Test |
|---|---|
| A missing score is never a zero | `ParameterScore.scored(x, 0)` raises; abstained parameters drop out of the average |
| A silent video gets no score, not a low one | `test_silent_video_is_not_evaluated_rather_than_scored_low` |
| A forgotten note does not halve the overall | `test_missing_note_does_not_score_as_zero` |
| Hidden hands never lower a rating | `test_hidden_hands_abstain_and_do_not_lower_the_rating` |
| Legitimate Hindi spelling variants are not errors | `test_nukta_optional`, `test_anusvara_equals_conjunct_nasal` |
| Unreadable handwriting abstains, never marks wrong | `test_unreadable_answer_abstains_rather_than_marking_wrong` |
| Genuinely wrong answers still count | `test_confidently_read_wrong_answer_is_scoreable` |
| Feedback is bilingual and jargon-free | `test_feedback_is_bilingual`, `test_no_parameter_names_leak_into_feedback` |

One consequence worth knowing: because abstaining removes a parameter from the
average, a submission with hidden hands can score *slightly higher* than the same
submission with hands visible. That is the design erring in the student's favour,
which is the intended direction — but it is a real effect, not an accident, and it
should be considered during calibration.

## Reading the handwritten Hindi

The riskiest part of note scoring. A misread marks a **correct** answer wrong, and the
student has no way to appeal.

The approach avoids open-vocabulary OCR entirely: the module ships the expected Hindi
for every row, so the question is only whether what was written matches a known
string — a much easier and more accurate problem than reading arbitrary handwriting.

`devanagari.py` keeps two numbers separate, and this distinction is the point:

* **read confidence** — how sure we are we read the handwriting (comes from the OCR
  or vision model). Below threshold → abstain.
* **similarity** — how close what we read is to the expected answer. Only meaningful
  once we trust the read.

Merging them would make a genuinely wrong answer indistinguishable from handwriting
we failed to parse, so either real errors vanish from the score or students are marked
wrong for our failure.

Tolerances applied: nukta optional (ज़/ज), anusvara equals conjunct nasal
(संबंध/सम्बन्ध), zero-width joiners and punctuation ignored, and a single wrong letter
in a long word treated as a slip rather than wrong knowledge.

## Plugging into the portal

Nothing in the scoring core reads a file, calls an API, or knows where a submission
came from. Integration means writing one small class per seam:

| Seam | Prototype today | Portal later |
|---|---|---|
| `SubmissionSource` | sample files in a folder | pending submissions from the portal |
| `ResultSink` | `JsonSubmissionStore` | ratings and note written back to the portal |
| `Transcriber` | supplied transcripts | a real ASR service |
| `VideoScorer` | `RuleBasedVideoScorer` | a vision/language model call |
| `NoteScorer` | `RuleBasedNoteScorer` | a vision model plus the same answer-key matching |
| `FeedbackWriter` | deterministic builder | a model, with the deterministic version as fallback |

Rules that cannot be enforced in Python — accents are never an error, never infer the
activity from posture, abstain rather than score low on thin evidence — are documented
at the top of `providers.py` so they land in the prompt of whatever model implements
those interfaces.

## Before this grades anyone

Two items from the design that code cannot satisfy:

1. **Consent.** Recording and processing children's video needs recorded
   parent/guardian consent first. This is the blocker.
2. **Calibration.** Have a teacher grade ~10 submissions by hand, compare per
   parameter, and agree what level of disagreement is acceptable. The rule-based
   scorers in this milestone are honest stand-ins, not a claim to accuracy — only
   Speed (computed words per minute) and Completion (counting filled rows) are real
   measurements today.
