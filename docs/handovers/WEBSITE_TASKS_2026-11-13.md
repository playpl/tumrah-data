# Tasks for the website agent (owner, 2026-11-13)

The data session never writes production. These three need the tumrah repo (`C:\Users\Ahmed\Desktop\tumrah`).
Data files are in `C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\modules\year2-cns\site\`.

## 1. Chapters come from the Telegram list (rewritten 2026-11-14, owner)
Chapters are NOT handout lectures. Each lesson's `chapter {title, order}` in `lessons.jsonl` is the item of the doctor's Telegram
list message it is posted under (Azony: Spinal cord, Medulla, Nuclei of medulla & Features of pons, Nuclei of pons & midbrain &
cerebellum, 4th ventricle). Same title in two doctors' lists = one chapter; order = first appearance per subject.
- `importHubData lessons` reports `chapters_to_create` (45 in the 11-14 dry run) and creates none: add chapter creation
  (title + order) and moving existing lessons without duplicates or orphans (questions, ranges, links stay attached).
  Dry run, then `--apply`. The legacy chapters (Spinal cord, Nervous tissue, Sensations) may end up empty.
- 4 lessons fall back to the subject's old chapter when the list names no item for them.

## 2. Cocci has no site doctor
Telegram list 1636 (Dr. Cocci, physiology) has one PDF ("Receptors tafreghat") and no lectures yet. The data side cannot
import him until a doctor exists on the site. Create the doctor profile (or the owner names an existing id) and tell the
data session the id; it then goes into `doctors_folder.ALIASES`.

## 3. Whiteboard notes have no place on the site
`lesson_files.jsonl` (new) lists per-lesson files: `{lesson: "lecture:cns-076", doctorId, kind: "whiteboard", name, file,
size, sha256}`. Today: Elsamahy's two "Ascending Tracts" PDFs (7.1 and 9.5 MB) on lessons cns-076 and cns-077.
The Lesson model has only `bookUrl` and CourseResource is student-owned, so there is nowhere to show them. Add a lesson
file store (private storage like the recordings, upload like `uploadLessonMedia.ts`) and show them on the lesson page.
Azony's "all his files on every lecture" rule needs the same thing.

## 4. Four Zahran mini lectures changed kind
`lessons.jsonl` now lists cns-093 Perikaryon, cns-094 Processes & Classification, cns-095 Ganglia (were `kind: lesson`)
as `kind: summary` with `covers` (cns-001, cns-004, cns-020), and adds cns-106 Nerve fiber (mini lecture, covers cns-019).
If the site already has cns-093 to cns-095 as plain lessons, the import must change their kind and `covers`, not duplicate them.
