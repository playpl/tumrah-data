# Tasks for the website agent (owner, 2026-11-13)

The data session never writes production. These three need the tumrah repo (`C:\Users\Ahmed\Desktop\tumrah`).
Data files are in `C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\modules\year2-cns\site\`.

## 1. Wrong chapters on the site
Every Dr. Azony lecture (and other auto-list lectures) shows under "Spinal cord". Cause was on the data side and is fixed
(commit "fix: file each lesson in the handout chapter its pages fall in"): `lessons.jsonl` now gives each lesson
`chapter {title, order}` = the handout lecture its pages fall in, per subject. Legacy names kept: Spinal cord, Nervous
tissue, Sensations. Orders are per subject and have gaps.
- Check `importHubData lessons --module year2-cns --file lessons.jsonl` creates the new chapters (title + order) and moves
  existing lessons without duplicates or orphans (questions, ranges, links stay attached). Dry run, then `--apply`.
- Verify on the site: Azony spreads over Spinal cord, brain stem nuclei, cerebellum, 4th ventricle.
- 5 lessons are not placed yet and stay in the first chapter (cns-075, 092 to 095).

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
