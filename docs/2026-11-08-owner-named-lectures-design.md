# Owner-named lectures (design, 2026-11-08, approved by the owner the same day)

Built: `lectures.create`/`set_ranges`, `flows/place.py` + `checks.check_place`, `shortlist.py` (shortlist, `send`,
`results`), lecture-scoped pointer jobs (`other_lecture`), the Lectures screen on the admin page. Waiting: mini
lectures and revisions (asked the website session what they are), `importHubData lectures` (after the website adds
`Lesson.handoutRanges` and LectureQuestion kind `doctor`), the labels flow without `lecture_id`.

The owner's rule: **there are no lectures until the owner names one.** The agent-made list of 64 CNS lectures
(`reference.json`) is out of use (kept in `modules/year2-cns/old/agent-lecture-list-2026-11-08/`). The lecture is the
unit of work and of publishing. The owner does the judging that only the owner can do. The agents do the rest.

## Who does what

| Step | Who | What |
|---|---|---|
| 1. Name the lecture | Owner | Module, title, doctor (picked from the site's doctors). Optional: recording file or YouTube link, site lesson. |
| 2. Place it in the handout | Agent | Finds the handout pages and lines the lecture teaches (one or more ranges). The owner sees the pages on the page and can correct them. |
| 3. The doctor's questions | Owner | Two lists: **Required** (the doctor's main questions) and **Doctor's other** (from the doctor, not required). |
| 4. Is it already ours? | Code, then agent | Every question the owner adds is looked up in the bank and on the site before anything new is made (see below). |
| 5. Other questions | Code, then agent | Quiz, past-exam, poll and AI questions that belong to the lecture become **Extra** (see "Shortlist"). |
| 6. Recording | Agent | Transcribe, word fixes (unsure ones to the owner), link each minute to handout lines: the existing flows. |
| 7. Books and highlights | Agent | Doctor-book lines on the lecture's handout lines, importance highlights: the existing flows, run on the lecture's lines. |
| 8. Publish | Code | Checker passed, audit sample agreed, importer dry run matches, then apply (task 22). |

On the site a lecture's questions then have three kinds: `required` (owner), `doctor` (owner, new kind), `extra` (agent).

## Step 3: how the owner picks the doctor's questions

A **Lecture** screen on the admin page, one lecture at a time:
- **Pick from the bank**: questions filtered to the lecture's module and this doctor (the labels flow already tags
  module and doctor from the channel headers), best shortlist matches first. Tick, then "Required" or "Doctor's other".
- **Add a file**: the doctor's sheet (JSONL, or pasted). Each question goes through step 4 first.

## Step 4: the owner's questions are looked up first

Reuses `cover.py`, which already does this for whole files:
1. Script, exact: the question's `word_key` (one changed word is a new question) against the bank and the site's
   81,125 questions. A match links to the existing question.
2. Agent, for the rest: each left question is shown beside up to 5 candidates that share its rare words; the agent
   answers the candidate's id or "none". The checker accepts only a listed candidate.
3. Only the ones still left are new questions. Their key comes from the owner's file; without one they wait.

## Step 5: the shortlist (the agent never reads the whole bank)

Code ranks the bank for one lecture, and the agents only point the top of that list:
1. **Free, no agent work**: questions the site already points into the lecture's handout lines.
2. **Rare-word score**: words that occur in the lecture's handout lines and are rare in the rest of the handout (the
   lecture's own terms: nuclei, tracts, drug names). A question scores by how many of them it shares, weighted by
   rarity. Common words ("nerve", "cell") count for almost nothing.
3. **Boosts**: same module (posting windows in `config.json`), same doctor label, repeated by doctors.
4. **Cut**: questions above a score floor, at most about 400 per lecture (set in `config.json`).
5. **Self-check**: the owner's Required questions are the answer key for the shortlist. If any of them would have
   ranked below the cut, the cut is too tight; the page shows the shortlist's recall on them, and the cut grows.

The pointer agents get the shortlist in batches of 25 and point each question to line IDs inside the lecture's ranges,
or answer "not this lecture". A "not this lecture" question stays free for other lectures. Pointed questions become
the lecture's Extra.

## What changes in code

- `lectures/<id>/lecture.json` gains `doctor` (site doctorId), `ranges` (handout line ID ranges), `required` and
  `doctor_questions` (question ids, in the owner's order).
- New flow `place` (step 2), new `shortlist.py` (step 5), the Lecture screen (steps 1, 3), `cover.py` reused (step 4).
- Pointer flow: payload limited to the lecture's ranges; "not this lecture" becomes a valid answer.
- Labels flow: keeps module and doctor, drops `lecture_id` (no fixed list any more).
- Site (tumrah repo): `LectureQuestion` kind `doctor`; how a lesson knows its handout lines (see below).

## Open for the owner

1. Step 2: should the agent find the handout pages (default), or will you type them?
2. A lecture can teach more than one part of the handout (several ranges). Right?
