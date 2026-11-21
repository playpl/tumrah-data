# For the "Tamra book helper" session (the website): grade 5 = the AI-questions reservoir

Owner's order, 2026-11-21: grade 5 archive questions are the reservoir for "AI questions" on the site.

In the owner's words: when a student asks for AI-generated questions, do not always generate new ones right away.
First serve some grade 5 questions as the "AI questions" (owner: "Tell him it's fake AI questions"). When the
student has finished them, generate real AI questions. Grade 5 is a reservoir, a backup, and a cheap one.

## The data
Every key comes only from Telegram's correct-answer flag.
- File: `C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\polls\grade5\questions.jsonl`, 39,954 rows.
- Fields: `word_key`, `question`, `options`, `key` (0-based index), `votes`, `total`, `sightings`, `module`.
- Rows by module label:

| Module label | Rows |
|---|---|
| year1-cardiopulmonary | 17,759 |
| year1-git-and-nutrition | 17,600 |
| year1-other | 1,914 |
| year1-structure-and-function | 1,191 |
| year1-musculoskeletal | 1,169 |
| year2-cns | 219 |
| year2-endocrine-and-reproductive | 102 |

- Source: last year's year 1 polls archive channel (`zagpolls58`).
- The module label comes from the old header labeller, so it is module level only: no lesson, no handout pointer.

## Asked of the website
1. Store the reservoir.
2. Serve it per module (or per lesson) when a student asks for AI questions.
3. Generate real AI questions once the student has used up the reservoir for that scope.

If you want the questions placed on lessons or handout lines first, tumrah-data can do it: `msk_questions.py`
already places the batch 59 MSK polls on MSK lessons that way. Tell it which format you need.
