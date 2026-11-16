# Owner's words, verbatim (2026-11-16 rebuild session)

Extracted by script from the session transcripts. Order = time order. Nothing is paraphrased.


## 1. Message

You will start the complete rebuild of this entire project. Get ready to fire Fable sub-agents to work with you. Plan everything at first with them.


## 2. Message

Wait, I did not give you the plan.


## 3. Message

<pasted_content id="a6e2">
1. Core Domain Architecture & Single Source of Truth (SSOT)
Governing Principle: The Handout as SSOT
 * Absolute Reference: The college Handout is the Bible and core programmatic backbone of the platform. It must never be modified or replaced; every other entity in the system (the Tumrah book, doctors' books, audio/video records, and questions) maps directly back to it.
 * Alignment Granularity: Mapping must happen at the Atomic Sentence / Fact Level, never at the full-page or whole-lesson level.
 * Strict Doctor Isolation: Each doctor is bound to a single subject with independent chapters, lessons, headings, and their own book (which is a structured reconstruction of the Handout, identical in nature to the Tumrah book).
| Dimension | Current Coverage Scope | Operational Rules |
|---|---|---|
| Universities & Years | Year 1: NU (Private/National) + ZU (Public)
Year 2: ZU (Public) only | Architect the schema for future expansion while enforcing current coverage boundaries. |
| Books (Tumrah + Doctors) | Structured reconstructions of the Handout | Aligned to the Handout at the sentence level; once linked to the Handout, all books automatically cross-link with one another. |
| Whiteboards | A3 study sheets, transcripts, mini-booklets | Uploaded as-is to a dedicated Whiteboards section linked strictly to their respective lecture—no further processing. |
| MCQ Files | Question banks authored by subject doctors (often released/updated incrementally) | Extract questions, link them to the doctor and book, then delete or archive the raw file (never treat as a standard document). |
| Misc. Manual Files | Minor standalone files | Excluded from automation (uploaded manually by you). |
2. Phased Execution Plan
Phase 0: Cleanup & Core Handout Graph
 * Legacy Data Purge: Delete all Year 1 Telegram Polls data. Preserve all existing Year 2 CNS Polls intact and prepare the ingestion schema for upcoming MSK channels.
 * Canonical Handout Graph: Parse and index the Handout into an addressable tree (University -> Year -> Subject -> Chapter -> Lesson -> Atomic Sentence ID) to serve as the immutable anchor for all downstream alignment.
Phase 1: Hybrid Book-to-Handout Alignment Engine
To eliminate the token waste and latency of having an LLM read an entire book to align a single sentence, execute alignment in three sequential layers:
 * Deterministic Code Pre-Filtering:
   * Segment both the Handout and the target book (Tumrah or a doctor's book) into atomic sentences/clauses.
   * Use Embeddings + BM25/Lexical Overlap via code to narrow the search space for each book sentence down to the top 5–10 candidate sentences within the corresponding Handout chapter/lesson.
 * AI Context-Window Aligner:
   * Feed a sliding window of consecutive book sentences alongside only the narrowed candidate slice to the LLM to resolve exact mappings (1-to-1, 1-to-Many, or Many-to-1).
 * Programmatic Audit & Verification:
   * Run automated checks for orphan sentences or erratic jumps, routing low-confidence mappings to a verification pass.
Phase 2: Telegram Ingestion & Linear Records Sync
 * Mother Message Inspection Agent:
   * Use an intelligent agent (not rigid regex/scripts) to read each doctor's Mother Message, locate the records section (Lectures / Records / Lessons), ignore PDFs, images, and summaries, and cache the parsed message map for fast subsequent checks.
   * Follow embedded hyperlinks and mirror any additions, edits, or deletions on Telegram directly onto the site.
 * Non-Blocking Immediate Upload:
   * As soon as a new audio record, video, or YouTube link is detected, upload it to the site immediately so students have instant access without waiting for transcription.
 * Async Transcription via Gemini Fleet (Antigravity):
   * Dispatch uploaded records in the background to Gemini Fleet (Antigravity)—respecting file size and duration limits via smart chunking when needed—to extract raw bilingual transcripts (Arabic speech + English medical terminology).
 * Linear Semantic Segmentation & Book Sync:
   * Pass the full raw transcript to a high-reasoning LLM to understand the lecture flow and divide it into sequential segments (ranging from two lines to several pages depending on the doctor's explanation) mapped to the doctor's book.
   * Strict Downward Monotonicity: Segments must progress strictly downward as audio playback advances—never jumping back upward on a page or lesson—ensuring smooth visual tracking for students.
   * Through Phase 1's graph, each audio segment automatically resolves to the Handout and the Tumrah book.
Phase 3: Questions Engine & Grading Hierarchy (Deferred to the End)
Hold this entire pipeline until Phases 0, 1, and 2 are fully operational:
| Grade | Source | System Role & Processing |
|---|---|---|
| Grade 4 | Telegram Polls
(Backbone & Reservoir) | Primary data reservoir collected via the automated voting flow (stored raw; unexposed on the frontend until linked/upgraded). |
| Grade 2 | Doctors' MCQ Books | Questions extracted from doctor PDFs (file then archived/deleted), matched against the Polls reservoir and poll headers, bound to the doctor, and tagged with Flag: Grade 2. |
| Grade 1 | Quiz Bot / Google Forms / Quizzes | Highest-priority questions on the platform; tightly bound to the specific doctor and lesson, and tagged with Flag: Grade 1. |
 * Question-to-Book/Handout Linking: Run code-based lexical/semantic similarity first to narrow down candidate book sections per question, then pass only the targeted snippet to the LLM for final sentence-level linkage.
3. Agent Execution Directive (Copy-Paste Prompt)
You are now responsible for re-architecting and rebuilding the Data Infrastructure and Ingestion Pipeline for the "Tumrah" platform, ensuring clean, accurate, and token-efficient data delivery to the production site.

### Non-Negotiable Architectural Rules:
1. **The Handout is the Single Source of Truth (SSOT):** Every entity in the system (Tumrah book, doctors' books, lectures, questions) must link back to the Handout at the finest possible granularity (Atomic Sentence / Fact Level)—never full pages or whole lessons. The Handout itself is immutable.
2. **Strict Doctor Isolation:** Each doctor is bound to a single subject with independent chapters, lessons, titles, and their own book.
3. **Non-Blocking Upload Rule:** Any newly detected audio record or video on Telegram must be uploaded to the site immediately. Transcription and alignment run asynchronously in the background.
4. **Execution Priority (CRITICAL):** Build and execute Phases 0, 1, and 2 completely first. **Leave the entire Questions Engine (Phase 3) for the very end**—do not process or upload questions until I provide the remaining specifications and MSK channel links.

---

### Step-by-Step Execution Plan:

#### 1. Cleanup & Core Handout Graph (Phase 0):
- Delete all existing Year 1 Telegram Polls data.
- Keep all Year 2 CNS Polls data intact and prepare the ingestion schema for MSK channels.
- Build the canonical Handout graph addressable down to the sentence level: `University [NU, ZU] -> Year [Y1, Y2] -> Subject -> Chapter -> Lesson -> Atomic Sentence ID`.

#### 2. Hybrid Book-to-Handout Alignment Engine (Phase 1):
- Never pass an entire book to an LLM to align a single sentence.
- Implement a 3-stage alignment pipeline for both the Tumrah book and doctors' books against the Handout:
  a) **Code Pre-Filtering:** Split texts into atomic sentences and use Embeddings + Lexical Overlap to narrow candidates for each sentence down to the top 5–10 matches within the same Handout lesson/chapter.
  b) **AI Context-Window Aligner:** Pass consecutive windows of book sentences alongside only the narrowed candidate slice to the LLM for exact sentence-level mapping.
  c) **Validation:** Programmatically audit for orphan sentences or erratic jumps, flagging low-confidence matches for review.
- Handle Whiteboards (A3 sheets / study summaries) by uploading them as-is to the dedicated Whiteboards section linked only to their lecture. Ignore miscellaneous manual files.

#### 3. Telegram Sync & Linear Records Pipeline (Phase 2):
- **Mother Message Parsing:** Use an intelligent LLM agent (not rigid regex) to read each doctor's Mother Message, isolate the lectures section (`Lectures` / `Records` / `Lessons`), ignore PDFs, images, and summaries, and cache the resulting structure for ongoing syncs.
- **Live Sync:** Follow hyperlinks and mirror any additions, updates, or deletions on Telegram directly on the site.
- **Async Transcription:** Immediately after uploading a record to the site, dispatch it in the background to **Gemini Fleet (Antigravity)**—respecting size and duration limits—to obtain the raw bilingual transcript (Arabic + English medical terms).
- **Linear Semantic Segmentation:** Have a reasoning LLM read the full transcript, segment it sequentially (from two lines to multiple pages depending on the doctor's explanation), and map each segment to the doctor's book. **Mandatory Constraint:** Mapping must be strictly monotonic downward as audio playback progresses—never jumping upward on a page.

Begin designing and implementing Phases 0, 1, and 2 immediately, and confirm readiness before moving to Phase 3.

Share the remaining question rules and the MSK Telegram channel details whenever you are ready so we can finalize Phase 3.
</pasted_content id="a6e2">


## 4. Message

Start with the token burning stuff first.


## 5. Message

I mean token burning on you. Read stuff and start searching with sub-agents. First, do not wait for codes.


## 6. Answers to my questions

The user answered: "What form should the rebuild take? Today there are 57 root scripts plus about 2,000 fleet job folders in this repo."="New package here (Recommended)", "Which model should do the reading work in the new engine (book sentence alignment, transcript segmentation, mother message parsing)?"="The fleet should work on the heavy lifting related to transcription. Gemini should align these transcriptions, and whatever you think is too heavy for Claude (because Claude is paid), then use the fleet. Keep in mind that the fleet is stupid, so do whatever you think is token-saving and money-saving, but without giving up any quality.", "Your plan says the pipeline uploads new records to the site at once and mirrors Telegram edits and deletions. When a lecture is deleted or replaced on Telegram, what should happen to it on the production site?"="Hide as draft (Recommended)", "What should happen to the existing AI results (88 book alignment jobs, lecture placements, 3,100 question pointers, ledger rows) when the new sentence-level engine arrives?"="Check their quality. See if they need any redo.". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.


## 7. Message

give me these questions again


## 8. Message

[Request interrupted by user for tool use]


## 9. Answers to my questions

The user answered: "Year 1 polls sit in three places: ZAG_59_Polls (all Year 1, 5,018 questions), zagpolls58 (batch 58's Year 1 archive: 40,450 Year 1, but also 219 labelled CNS and 102 endocrine), and 1,097 Year-1-labelled questions inside Batch58ATM (the Year 2 channel; labels there were made by the fleet, not by you). What exactly should be deleted?"="https://t.me/zagpolls58 This is the archive for year one. Gather all the questions, set them as grade 5 questions dealing with it later, except the repeated one. Remove them from here completely. 

https://t.me/Batch58ATM second year's backbone 
https://t.me/ZAG_59_Polls first year's backbone 

Friendly reminder about my constitutional rules: the handout is the heart of everything. Every question is linked to the handout. We know a question is for this lecture since they both land on the same area in the handout.

To make it easier, if we have a quiz that is specific to such a lecture, in the polls, if we have a section of the polls, the polls are not orphans. They always have titles. Everything is going to point somewhere to make it easier to point, so we don't just search in the entire book for everything for one question.

Make it simpler. Make a very good system so we don't end up in a situation where we miss a quiz exam outside somewhere, outside of a lecture, because that would be stupid. 

Extra stuff I forgot to tell you about. I told you the doctors will be having exams or tests or quizzes, whatever you call it, after every lecture and/or some of the lectures.

Now we will gather them from here, starting from this message onward, and do not read the files. Skip the files. Get the links only. If you're confused which is which, ask me.

Some of these might be for entire chapters, so you're going to have to separate them. Some are for lessons, and some lessons don't get any. If you can't find the questions lesson or the testis lesson, ask me. 

Something extra I did not tell you about: I told you that I'm going to get you all the quizzes after the lectures and quizzes. Some of them might be for the entire chapter, so you're going to have to split them manually. Some quizzes are going to be in files, some are going to be in Quizbot, and some are going to be in Google Forms.

Gather all of these quizzes and treat them as grade 1 for the student with this doctor, and it only appears for this student.

The second thing is the files: you're going to have to figure out what this file is on each update or the first time you gather it. You remember, you're just a planner. You're going to have to figure this out: what this is and where it came from. Where did it come from? What is inside here, and what does it cover? Maybe it covers the entire module for this doctor. As I told you, each doctor has his own file, so from the content, you're going to understand it. If you can't, just tell me.

This is your file, and these are your quizzes, so you get them from these two channels. It's going to follow the tree architecture using hyperlinks. 

https://t.me/zagexam59/503

and this is for year two https://t.me/ZMSUMcqs58/2098", "Batch58ATM also holds Year 2 polls that are not CNS: 22,595 endocrine-and-reproductive and 4,305 other Year 2, plus 1,013 unlabelled. Your plan only says to delete Year 1 and keep CNS. What happens to these?"="No. That channel is going to work for year 1 only, not for 2. Delete them all. Do not archive them. Delete them. Remember, also, we are working on MSK for year 1 and CNS for year 2.", "Deleting poll data cannot be undone, and voting again costs days of account quota. The same Year 1 data also exists in about 320 MB of backup files (polls.before-*.db, questions.before-* in polls/ and bank/). How final should the deletion be?"="Wait, did I tell you to delete anything except for the one in the next and the previous question? I did not tell you to delete anything. The data is good. Just update it for everything other than the year 2 from the previous question.". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.


## 10. Message

[Request interrupted by user]


## 11. Message

Start this in a new session with all the details that it would miss if it was not you. Everything.
