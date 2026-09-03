"""Bilingual feedback assembly.

The written note is the part the student actually reads, so it matters more
than the numbers. It should sound like a good teacher writing in the margin of
a notebook: crisp, plain and specific.

Rules enforced here:
  * Two to four short sentences. Not a report.
  * English and Hindi, always. Feedback a student cannot read is worthless.
  * One specific strength first, then one concrete next step.
  * No jargon, no parameter names dumped in, no repeated scores, no comparison
    to other students.

This module composes the *structure* of the note from scored parameters. A
model-written version (warmer, more specific to what actually happened in the
recording) plugs in via ``providers.FeedbackWriter`` and should follow the same
rules; this deterministic version is the fallback and the test baseline.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .models import (
    ArtifactResult,
    GradedSubmission,
    ParameterScore,
    StudentMessage,
    TrendLabel,
)
from .rubric import Rubric
from .trend import trend_phrase

# Plain-language praise and next-step wording per parameter, in both languages.
# Deliberately actionable: "look up at the camera after each sentence", never
# "your confidence is low".
_STRENGTH = {
    "confidence": ("you spoke steadily", "आपने स्थिर आवाज़ में बोला"),
    "vocabulary": ("you used the new words well", "आपने नए शब्दों का अच्छा उपयोग किया"),
    "tone": ("your voice was warm and clear", "आपकी आवाज़ स्पष्ट और मधुर थी"),
    "hand_gesture": ("your hand movements looked natural", "आपके हाथों के इशारे स्वाभाविक थे"),
    "speed": ("your reading pace was comfortable", "आपकी पढ़ने की गति सही थी"),
    "completion": ("you finished the whole task", "आपने पूरा काम पूरा किया"),
    "accuracy": ("your meanings were correct", "आपके अर्थ सही थे"),
    "comprehension": ("you explained the ideas in your own words",
                      "आपने विचारों को अपने शब्दों में समझाया"),
    "presentation": ("your note was neat and well organised",
                     "आपका नोट साफ़ और व्यवस्थित था"),
}

_NEXT_STEP = {
    "confidence": ("look up at the camera after each sentence",
                   "हर वाक्य के बाद कैमरे की ओर देखें"),
    "vocabulary": ("try to use two or three of the new words from the list",
                   "सूची में से दो-तीन नए शब्द बोलने की कोशिश करें"),
    "tone": ("read a little more warmly, as if explaining to a friend",
             "थोड़ा और सहज होकर पढ़ें, जैसे किसी दोस्त को समझा रहे हों"),
    "hand_gesture": ("hold the camera a little further back so your hands show",
                     "कैमरा थोड़ा दूर रखें ताकि आपके हाथ दिखें"),
    "speed": ("pause for one second after each full stop",
              "हर पूर्ण विराम के बाद एक सेकंड रुकें"),
    "completion": ("finish every item on the list",
                   "सूची का हर हिस्सा पूरा करें"),
    "accuracy": ("check your meanings against the article before you write",
                 "लिखने से पहले लेख से अर्थ मिला लें"),
    "comprehension": ("write each point in your own words instead of copying",
                      "हर बिंदु नकल करने के बजाय अपने शब्दों में लिखें"),
    "presentation": ("keep one line per word so the page stays easy to read",
                     "हर शब्द एक पंक्ति में लिखें ताकि पन्ना पढ़ने में आसान रहे"),
}


def _best_and_weakest(
    *artifacts: ArtifactResult,
) -> tuple[Optional[ParameterScore], Optional[ParameterScore]]:
    """Highest- and lowest-scoring assessed parameters across the submission."""
    assessed: list[ParameterScore] = []
    for art in artifacts:
        assessed.extend(art.assessed_scores)
    if not assessed:
        return None, None
    best = max(assessed, key=lambda s: s.value)
    weakest = min(assessed, key=lambda s: s.value)
    return best, weakest


def build_feedback(
    graded: GradedSubmission,
    rubric: Rubric,
    *,
    trend: Optional[TrendLabel] = None,
) -> StudentMessage:
    """Compose the student-facing note in English and Hindi."""
    en: list[str] = []
    hi: list[str] = []

    # 1. If something could not be evaluated, that comes first and plainly —
    #    the student needs to act on it, and it explains a missing score.
    for artifact in (graded.video, graded.note):
        msg = artifact.student_message
        if msg is not None:
            en.append(msg.en)
            hi.append(msg.hi)

    best, weakest = _best_and_weakest(graded.video, graded.note)

    # 2. One specific strength, named first — never generic praise.
    if best is not None and best.parameter in _STRENGTH:
        s_en, s_hi = _STRENGTH[best.parameter]
        en.append(f"Good work — {s_en}.")
        hi.append(f"अच्छा काम — {s_hi}।")

    # 3. One concrete next step, phrased as an action.
    #    Only when there is genuine room to improve: telling a student scoring
    #    5/5 to fix something is noise.
    if weakest is not None and weakest.value < 5 and weakest.parameter in _NEXT_STEP:
        n_en, n_hi = _NEXT_STEP[weakest.parameter]
        en.append(f"Next time, {n_en}.")
        hi.append(f"अगली बार, {n_hi}।")

    # 4. Trend, as a sentence rather than a badge.
    t_en, t_hi = trend_phrase(trend)
    if t_en:
        en.append(t_en)
        hi.append(t_hi)

    if not en:
        en.append("We could not evaluate this submission. Please upload your work again.")
        hi.append("हम इस काम की जाँच नहीं कर सके। कृपया अपना काम दोबारा अपलोड करें।")

    # Keep it to four sentences maximum. Not a report.
    return StudentMessage(en=" ".join(en[:4]), hi=" ".join(hi[:4]))
