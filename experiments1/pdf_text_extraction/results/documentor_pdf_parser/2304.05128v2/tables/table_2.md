# Table 3

ID: 00000064
Page: 8
BBox: [251, 569, 994, 884]

## Markdown Table

| Spider | Codex | GPT-3.5 | GPT-4 | StarCoder |
| --- | --- | --- | --- | --- |
| Baseline | 81.3 | 71.1 | 73.2 | 64.7 |
| Simple | 81.3 | 72.2 | 73.4 | 64.9 |
| +Expl. | 84.1 | 72.2 | 73.6 | 64.9 |

| TransCoder | Codex | GPT-3.5 | GPT-4 | StarCoder |
| --- | --- | --- | --- | --- |
| Baseline | 80.4 | 89.1 | 77.3 | 70.0 |
| Simple | 89.3 | 91.6 | 80.9 | 72.9 |
| UT | 91.6 | 92.7 | 88.8 | 76.4 |
| + Expl. | 92.5 | 92.7 | 90.4 | 76.6 |
| + Trace. | 87.9 | 92.3 | 89.5 | 73.6 |

| MBPP | Codex | GPT-3.5 | GPT-4 | StarCoder |
| --- | --- | --- | --- | --- |
| Baseline | 61.4 | 67.6 | 72.8 | 47.2 |
| Simple | 68.2 | 70.8 | 78.8 | 50.6 |
| UT | 69.4 | 72.2 | 80.6 | 52.2 |
| + Expl. | 69.8 | 74.2 | 80.4 | 52.2 |
| + Trace. | 70.8 | 72.8 | 80.2 | 53.2 |

## DataFrame Info

Shape: (15, 5)
Columns: ['Spider', 'Codex', 'GPT-3.5', 'GPT-4', 'StarCoder']

### DataFrame Preview

|    | Spider     | Codex   | GPT-3.5   | GPT-4   | StarCoder   |
|---:|:-----------|:--------|:----------|:--------|:------------|
|  0 | Baseline   | 81.3    | 71.1      | 73.2    | 64.7        |
|  1 | Simple     | 81.3    | 72.2      | 73.4    | 64.9        |
|  2 | +Expl.     | 84.1    | 72.2      | 73.6    | 64.9        |
|  3 | TransCoder | Codex   | GPT-3.5   | GPT-4   | StarCoder   |
|  4 | Baseline   | 80.4    | 89.1      | 77.3    | 70.0        |
|  5 | Simple     | 89.3    | 91.6      | 80.9    | 72.9        |
|  6 | UT         | 91.6    | 92.7      | 88.8    | 76.4        |
|  7 | + Expl.    | 92.5    | 92.7      | 90.4    | 76.6        |
|  8 | + Trace.   | 87.9    | 92.3      | 89.5    | 73.6        |
|  9 | MBPP       | Codex   | GPT-3.5   | GPT-4   | StarCoder   |
