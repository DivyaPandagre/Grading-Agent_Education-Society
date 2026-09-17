# EduGrade AI

An agent that evaluates student homework submitted through the WesFellow Hub
learning portal, checks it against the module it was set for, and writes feedback
in English and Hindi for a teacher to review.

Built for Wazir Education Society.

---

## Where things live

```
Hackhathon _EduGrade AI/    the code — one notebook
Module/                     module screenshots and text
Homework/handnotes/         photographs of student pages
Homework/videos/            student recordings
```

The three sample folders are in `.gitignore`. They hold real children's work and
none of it belongs in a shared repository — only the empty folders are committed,
so the structure is there when someone clones it. Put your own copies in locally.

**No code in this repository reads `Homework/videos/`.** Video and face frames of
a minor never reach the model. That is a deliberate line rather than an
oversight: if video grading is built later, frames are sampled and scored on our
own machine, and only the resulting numbers move forward.

## What is here

One notebook: **`Handnote_Feedback.ipynb`**. It handles the handwritten page —
reads the module, reads the student's page, checks one against the other, and
writes the feedback. Video comes later.

Five steps. Two of them use a model, and both are labelled in the notebook.

| Step | What it does | Needs the API key |
|---|---|---|
| 1 | Setup | no |
| 2 | The module — title, instruction, answer key | no |
| 3 | Read the handwriting off the photo | **yes** |
| 4 | Check what was read against the module | no |
| 5 | Write the feedback | **yes** |

**Step 4 is where every decision is made, and it uses no AI.** The model reads
and writes; plain code counts and compares. That split is deliberate — a teacher
can argue with a number that came from counting, and the feedback writer is given
the findings only, never the answer key, so nothing it says can move a mark.

## The three outcomes

Step 4 reaches one of three verdicts, and the feedback differs completely
depending on which.

**Marked against the module** — how many words were written, how many Hindi
meanings match the key, and one thing to work on next.

**A different module's homework** — the page header names another task. Nothing
is marked, nothing is marked *down*, and the student is told to ask their teacher
to move it to the right slot. This check runs **before** the marking on purpose:
scoring a page against an answer key it was never meant for produces a near-zero
for work the child did correctly.

**Not readable, or not a homework page** — no scores at all. An unreadable
photograph is our problem, not the student's, and must never produce a low mark.

---

## Running it

**1. Install the two packages**

```powershell
python -m pip install openai-agents python-dotenv
```

**2. Add your API key.** Create a file called `.env` next to the notebook, with
one line:

```
OPENAI_API_KEY=sk-...
```

`.env` is gitignored and must stay that way. A key committed once is in the
history forever.

**3. Supply an image.** Put a photograph of a handwritten page into
`Homework/handnotes/`, then point `HANDNOTE` in step 3 at it:

```python
HANDNOTE = "../Homework/handnotes/your_page.png"
```

Those files are gitignored, so they stay on your machine.

**4. Run it**

```powershell
cd "Hackhathon _EduGrade AI"
jupyter notebook Handnote_Feedback.ipynb
```

Steps 1, 2 and 4 run with no key. Steps 3 and 5 call the model and need credit on
the OpenAI account — reading one page costs roughly a cent.

---

## Known gaps

**The answer key is incomplete.** The Day 12 module lists 20 tough words; the
screenshot it was copied from cuts off after the 11th. Step 4 therefore refuses
to report a completeness percentage — against 11 it would flatter the student,
against 20 it would penalise them. Add the remaining nine and that check switches
on.

**The module is hardcoded.** Step 2 holds the Day 12 task as a literal. The real
one lives in Supabase, in `wes_scheduled_tasks` (`title`, `description`).

**No video yet.** The submission also carries a recording of the student reading
aloud. Not handled here.

**No teacher screen yet.** `ui_preview.png` shows the intended layout — verdict
first, then the findings, then an editable feedback box. Not built.

---

## Notes for whoever picks this up

The database is Supabase. Two tables matter: `wes_scheduled_tasks` holds the
modules, and `student_task_feedback` holds both the submission links and the
teacher's own past feedback in `feedback_notes`.

That second one is the interesting one. Teachers there don't score homework out
of five — they verify or reject it and write a note. So there is a real history of
accept/reject decisions to check the agent's verdicts against, and a large body of
real teacher wording to learn the tone from.

When selecting from `students`, take `id`, `student_id`, `name` and `class_id`
only. That table also holds `dob`, `bank_name`, `account_number` and `ifsc_code`.
