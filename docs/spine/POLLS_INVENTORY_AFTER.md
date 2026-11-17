```
POLLS INVENTORY (read-only; nothing was changed)

Channels (polls/channels.json):
  ZAG_59_Polls  ZU batch 59, year 1 backbone, grade 4, harvest yes
  Batch58ATM    ZU batch 58, year 2 backbone, grade 4, harvest yes, drops year2-endocrine-and-reproductive, year2-other
  zagpolls58    ZU batch 58, year 1 archive, grade 5, harvest no, store polls/grade5/questions.jsonl

polls.db rows, channel x label:
  ZAG_59_Polls: 6,031 rows; dupe 732, keyed 5,179, need 120; own votes 5,179; raw messages 12,629
      year1-cardiopulmonary                      1
      year1-musculoskeletal                    593
      year1-other                              590
      year1-structure-and-function           4,847
  Batch58ATM: 24,708 rows; dupe 735, held 1, keyed 23,972; own votes 24,271; raw messages 56,583
      (no label)                             1,066
      year1-cardiopulmonary                    270
      year1-git-and-nutrition                  826
      year1-structure-and-function               7
      year2-cns                             22,539
  zagpolls58: 0 rows; ; own votes 0; raw messages 0

bank/questions.jsonl: 35,942 questions, seen in x label:
  Batch58ATM                                 (no label)                                41
  Batch58ATM                                 year1-cardiopulmonary                    270
  Batch58ATM                                 year1-git-and-nutrition                  822
  Batch58ATM                                 year2-cns                             21,760
  Batch58ATM+quiz/form/book                  (no label)                               972
  Batch58ATM+quiz/form/book                  year1-structure-and-function               5
  Batch58ATM+quiz/form/book                  year2-cns                                 92
  ZAG_59_Polls                               year1-cardiopulmonary                      1
  ZAG_59_Polls                               year1-musculoskeletal                    217
  ZAG_59_Polls                               year1-other                              500
  ZAG_59_Polls                               year1-structure-and-function           4,120
  ZAG_59_Polls+quiz/form/book                year1-musculoskeletal                     48
  ZAG_59_Polls+quiz/form/book                year1-other                               32
  ZAG_59_Polls+quiz/form/book                year1-structure-and-function             100
  quiz/form/book                             (no label)                               967
  quiz/form/book                             none                                     167
  quiz/form/book                             year1-cardiopulmonary                    897
  quiz/form/book                             year1-git-and-nutrition                1,022
  quiz/form/book                             year1-musculoskeletal                    828
  quiz/form/book                             year1-other                              137
  quiz/form/book                             year1-structure-and-function           1,284
  quiz/form/book                             year2-cns                                 10
  quiz/form/book                             year2-endocrine-and-reproductive       1,638
  quiz/form/book                             year2-other                               12

polls/ready/questions.jsonl: 28,980 questions

CHANGE A: delete the non-CNS Year 2 polls of Batch58ATM (for good, no archive)
  own votes of those rows: 0
  bank questions deleted: 0
  ready questions deleted: 0

CHANGE B: move zagpolls58 (Year 1 archive) to the grade 5 store; nothing destroyed
  bank questions moved to grade 5: 0
  ready questions moved to grade 5: 0

Questions that stay but lose a sighting (repeated in a kept channel or in a quiz, form or book): 0

Kept untouched: 35,942 bank questions
```
