```
POLLS INVENTORY (read-only; nothing was changed)

Channels (polls/channels.json):
  ZAG_59_Polls  ZU batch 59, year 1 backbone, grade 4, harvest yes
  Batch58ATM    ZU batch 58, year 2 backbone, grade 4, harvest yes, drops year2-endocrine-and-reproductive, year2-other
  zagpolls58    ZU batch 58, year 1 archive, grade 5, harvest no, store polls/grade5/questions.jsonl

polls.db rows, channel x label:
  ZAG_59_Polls: 6,031 rows; dupe 852, keyed 5,179; own votes 5,179; raw messages 12,629
      year1-cardiopulmonary                      1
      year1-musculoskeletal                    593
      year1-other                              590
      year1-structure-and-function           4,847
  Batch58ATM: 54,972 rows; dupe 3,186, held 1, keyed 51,785; own votes 52,558; raw messages 56,583
      (no label)                             1,066
      year1-cardiopulmonary                    270
      year1-git-and-nutrition                  826
      year1-structure-and-function               7
      year2-cns                             22,539
      year2-endocrine-and-reproductive      25,628
      year2-other                            4,636
  zagpolls58: 48,582 rows; keyed 48,582; own votes 49,775; raw messages 49,575
      year1-cardiopulmonary                 21,804
      year1-git-and-nutrition               20,478
      year1-musculoskeletal                  1,381
      year1-other                            2,407
      year1-structure-and-function           2,118
      year2-cns                                226
      year2-endocrine-and-reproductive         168

bank/questions.jsonl: 102,565 questions, seen in x label:
  Batch58ATM                                 (no label)                                41
  Batch58ATM                                 year1-cardiopulmonary                    269
  Batch58ATM                                 year1-git-and-nutrition                  817
  Batch58ATM                                 year2-cns                             21,760
  Batch58ATM                                 year2-endocrine-and-reproductive      22,368
  Batch58ATM                                 year2-other                            4,301
  Batch58ATM+quiz/form/book                  (no label)                               972
  Batch58ATM+quiz/form/book                  year1-structure-and-function               5
  Batch58ATM+quiz/form/book                  year2-cns                                 92
  Batch58ATM+quiz/form/book                  year2-endocrine-and-reproductive         216
  Batch58ATM+quiz/form/book                  year2-other                                4
  Batch58ATM+zagpolls58                      year1-cardiopulmonary                      1
  Batch58ATM+zagpolls58                      year1-git-and-nutrition                    5
  Batch58ATM+zagpolls58                      year2-endocrine-and-reproductive          11
  ZAG_59_Polls                               year1-musculoskeletal                    173
  ZAG_59_Polls                               year1-other                              500
  ZAG_59_Polls                               year1-structure-and-function           3,459
  ZAG_59_Polls+quiz/form/book                year1-musculoskeletal                     29
  ZAG_59_Polls+quiz/form/book                year1-other                               32
  ZAG_59_Polls+quiz/form/book                year1-structure-and-function              57
  ZAG_59_Polls+zagpolls58                    year1-cardiopulmonary                      1
  ZAG_59_Polls+zagpolls58                    year1-musculoskeletal                     44
  ZAG_59_Polls+zagpolls58                    year1-structure-and-function             661
  ZAG_59_Polls+zagpolls58+quiz/form/book     year1-musculoskeletal                     19
  ZAG_59_Polls+zagpolls58+quiz/form/book     year1-structure-and-function              43
  quiz/form/book                             (no label)                               967
  quiz/form/book                             none                                     167
  quiz/form/book                             year1-cardiopulmonary                    896
  quiz/form/book                             year1-git-and-nutrition                1,022
  quiz/form/book                             year1-musculoskeletal                    797
  quiz/form/book                             year1-other                              137
  quiz/form/book                             year1-structure-and-function           1,273
  quiz/form/book                             year2-cns                                 10
  quiz/form/book                             year2-endocrine-and-reproductive       1,422
  quiz/form/book                             year2-other                                8
  zagpolls58                                 year1-cardiopulmonary                 17,759
  zagpolls58                                 year1-git-and-nutrition               17,600
  zagpolls58                                 year1-musculoskeletal                  1,169
  zagpolls58                                 year1-other                            1,914
  zagpolls58                                 year1-structure-and-function           1,191
  zagpolls58                                 year2-cns                                219
  zagpolls58                                 year2-endocrine-and-reproductive          91
  zagpolls58+quiz/form/book                  year1-cardiopulmonary                      1
  zagpolls58+quiz/form/book                  year1-musculoskeletal                     31
  zagpolls58+quiz/form/book                  year1-structure-and-function              11

polls/ready/questions.jsonl: 95,866 questions

CHANGE A: delete the non-CNS Year 2 polls of Batch58ATM (for good, no archive)
  polls.db   Batch58ATM year2-endocrine-and-reproductive      25,628 rows
  polls.db   Batch58ATM year2-other                            4,636 rows
  own votes of those rows: 28,287
  bank questions deleted: 26,669
      seen in Batch58ATM                               year2-endocrine-and-reproductive      22,368
      seen in Batch58ATM                               year2-other                            4,301
  ready questions deleted: 26,669

CHANGE B: move zagpolls58 (Year 1 archive) to the grade 5 store; nothing destroyed
  polls.db   zagpolls58 year1-cardiopulmonary                 21,804 rows
  polls.db   zagpolls58 year1-git-and-nutrition               20,478 rows
  polls.db   zagpolls58 year1-musculoskeletal                  1,381 rows
  polls.db   zagpolls58 year1-other                            2,407 rows
  polls.db   zagpolls58 year1-structure-and-function           2,118 rows
  polls.db   zagpolls58 year2-cns                                226 rows
  polls.db   zagpolls58 year2-endocrine-and-reproductive         168 rows
  bank questions moved to grade 5: 39,954
      seen in Batch58ATM+zagpolls58                    year2-endocrine-and-reproductive          11
      seen in zagpolls58                               year1-cardiopulmonary                 17,759
      seen in zagpolls58                               year1-git-and-nutrition               17,600
      seen in zagpolls58                               year1-musculoskeletal                  1,169
      seen in zagpolls58                               year1-other                            1,914
      seen in zagpolls58                               year1-structure-and-function           1,191
      seen in zagpolls58                               year2-cns                                219
      seen in zagpolls58                               year2-endocrine-and-reproductive          91
  ready questions moved to grade 5: 39,954

Questions that stay but lose a sighting (repeated in a kept channel or in a quiz, form or book): 1,037
      seen in Batch58ATM+quiz/form/book                year2-endocrine-and-reproductive         216
      seen in Batch58ATM+quiz/form/book                year2-other                                4
      seen in Batch58ATM+zagpolls58                    year1-cardiopulmonary                      1
      seen in Batch58ATM+zagpolls58                    year1-git-and-nutrition                    5
      seen in ZAG_59_Polls+zagpolls58                  year1-cardiopulmonary                      1
      seen in ZAG_59_Polls+zagpolls58                  year1-musculoskeletal                     44
      seen in ZAG_59_Polls+zagpolls58                  year1-structure-and-function             661
      seen in ZAG_59_Polls+zagpolls58+quiz/form/book   year1-musculoskeletal                     19
      seen in ZAG_59_Polls+zagpolls58+quiz/form/book   year1-structure-and-function              43
      seen in zagpolls58+quiz/form/book                year1-cardiopulmonary                      1
      seen in zagpolls58+quiz/form/book                year1-musculoskeletal                     31
      seen in zagpolls58+quiz/form/book                year1-structure-and-function              11

Kept untouched: 34,905 bank questions

LOOK AT THIS BEFORE APPLYING:
  archive question labelled year2-cns (grade5): 219
  archive question labelled year2-endocrine-and-reproductive (grade5): 102
```
