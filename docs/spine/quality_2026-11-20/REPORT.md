# Quality check: Gemini transcripts and lecture-to-book segmentation (2026-11-20)

Owner asked: "are your transcription with Gemini and aligning of lecture with the book precise, accurate, high
quality?" The full seg run was stopped first (the owner said "measure first"). Everything below is measured; what
is not measured says so.

## 1. Segmentation (transcript paragraph -> doctor's book lines)

Sample: 50 paragraphs, 2 random per lecture from the 25 lectures `seg dry` accepts (seed 20261120;
`seg_sample.py`, the paragraphs and book lines shown in `seg_sample.txt`). Claude read each paragraph (Arabic) and
the book lines reader A gave it. Verdicts with notes: `seg_verdicts.json`.

| Verdict | Count |
|---|---|
| right | 42 |
| right but wide (many lines, or a whole table row) | 4 |
| wrong | 2 |
| unsure (book slice not checked) | 2 |

- Error rate on accepted lectures: 2 of 50 = 4% (95% interval roughly 0.5% to 14%); 4 to 8% counting the unsure.
- The two wrong: cns-010 P189 (right line plus two wrong extra lines), cns-013 P21 (NONE where the paragraph starts
  the definition of a receptor).
- Agreement is not proof: readers A and B gave the identical answer on 26 of 50, and the wrong cns-013 P21 is one of
  them. Two Hydrogen chats make the same mistakes, so "accepted (agree 90%+)" overstates certainty.
- Limits that are not the reader's: book tables extracted as one line per row (all cells of "Shape" in one line),
  scrambled table text (Basel's receptors table, cns-038), page footers as book lines ("Dr. Basel Sherif CNS Module").
  Links into those lines can only be as fine as the line.

## 2. Transcripts

263 transcripts scanned (`tx_scan.py`, `dup_scan.py`); 20 pieces heard a second time on Gemini 4 Hydrogen and
compared (`rehear.py`).

**YouTube auto-captions (28 CNS lectures: cns-001..006, 011..014, 017, 018, 151..162, 186..189).** English medical
terms are dropped or written in Arabic letters, no punctuation. Worst: cns-006 (15.5 dropped-term holes per 1000
words, e.g. "بيغيروا ال بتاع ال"), cns-001 (7.9), cns-158 (5.3). Segmentation still worked on several (cns-001..006
accepted) but these are the weakest transcripts.

**Heard transcripts (83 CNS lectures; fleet era and Gemini).**
- Repeated passages (a piece heard twice or a reader looping), 40+ words: 13 of 83. Serious: cns-010 (a 1,177-word
  passage twice, 16% of the transcript, plus a loop "الممبرين اللي نتج من ..."), cns-037 (11%). The other 11 are
  0.3-2.4% of their words.
- `[cite: N]` junk tags (Gemini web) in 23 transcripts: harmless to meaning, should be stripped.

**Second hearing of 20 random pieces (one per lecture, 5 minutes each).**
- 18 of 20: the two hearings carry the same content; text only on one side is at most 4% (median 0%). Raw word
  agreement looks low (median 71%) only because one copy writes "dorsal root" and the other "دورسال روت".
- 2 of 20 (cns-037 c00, cns-084 c03): the old transcript has about 42% repeated text; the new hearing is clean.
- One real content gap: cns-077 c02, the new hearing has a sentence on substance P (slow pain) that the old lacks.
- Not measured: whether both hearings share the same mistake (wrong word, invented sentence). Two hearings by the
  same model can agree and both be wrong. That needs a human ear: 5 pieces wait for the owner in
  `listen_2026-11-20/` (not in git; README inside).

## 3. Handout placement of lectures

71 CNS lectures are placed by title only (`placed_by: claude-coarse`: the 54 of 2026-11-20 plus 17 today). Nobody
checked them against the recordings. Khaled's "ECG" (cns-188) is on Brain waves/EEG pp. 253-256: a guess.

## 4. Book -> handout (P1)

The only one audited before: 200-link audit per book, 126 read, 0 wrong (`docs/spine/HANDOVER.md`).

## What this means

- Segmentation on accepted lectures: about 92-96% right in this sample, coarse where the book line is coarse.
- Transcripts: Gemini Hydrogen re-hearings are consistent; the defects found are in old transcripts (repeats) and in
  YouTube captions (dropped terms). Accuracy against the audio is unmeasured until the owner listens.

## Fixes this points to (not done yet)

1. Re-hear on Hydrogen the transcripts with 40+ word repeats (13) and the worst YouTube captions (cns-006, 001,
   158, 003, 002), then redo their seg jobs.
2. Strip `[cite: N]` from transcripts.
3. Judge with a third check, not A=B agreement alone (e.g. a gold set of read paragraphs per book, like this one).
4. Place the 71 coarse lectures from their recordings once transcribed.
