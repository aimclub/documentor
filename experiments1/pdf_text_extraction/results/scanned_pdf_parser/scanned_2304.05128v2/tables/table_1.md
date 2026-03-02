# Table 2

ID: 00000063
Page: 8
BBox: [228, 199, 957, 491]

## Markdown Table



## DataFrame Info

Shape: (10, 4)
Columns: ['(a) Results on the Spider development set.', '(b) Results on MBPP dataset.', '', '']

### DataFrame Preview

|    | (a) Results on the Spider development set.   | (b) Results on MBPP dataset.   |                            |             |
|---:|:---------------------------------------------|:-------------------------------|:---------------------------|:------------|
|  0 | Spider (Dev)                                 | n samples                      |                            |             |
|  1 | w/training                                   | Prior work                     |                            |             |
|  2 | T5-3B + N-best Ranking                       | 80.6                           | MBR-Excc                   | 63.0 (n 25) |
|  3 | LEVER (Ni et al., 2023)                      | 81.9                           | Reviewer                   | 66.9 (n 25) |
|  4 | Prompting only w/o debugging                 | LEVER                          | 68.9 (n 100)               |             |
|  5 | Coder-Reviewer                               | 74.5                           | SELF-DEBUGGING (this work) |             |
|  6 | MBR-Excc                                     | 75.2                           | Codex                      | 72.2 (n 10) |
|  7 | SELF-DEBUGGING (this work)                   | Simple                         | 73.6                       |             |
|  8 | Codex                                        | 81.3                           | UT                         | 75.2        |
|  9 | + Expl.                                      | 84.1                           | UT + Expl.                 | 75.6        |
