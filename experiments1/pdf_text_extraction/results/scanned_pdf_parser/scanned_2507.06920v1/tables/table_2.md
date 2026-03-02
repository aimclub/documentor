# Table 3

ID: 00000073
Page: 7
BBox: [210, 222, 1017, 592]

## Markdown Table

| Method / Configuration                       | DR@20   | DR@50   | VAcc@20   | VAcc@50   | AUC@50   | DivRatio@50   |
|:---------------------------------------------|:--------|:--------|:----------|:----------|:---------|:--------------|
| Main Comparison with Baseline TCG Methods    |         |         |           |           |          |               |
| TestChain [22]                               | 65.91%  | 68.31%  | 8.12%     | 11.88%    | 0.0841   | 50.09%        |
| Input-Interpreter (LiveCodeBench-style [19]) | 77.84%  | 81.07%  | 12.36%    | 16.72%    | 0.1234   | 79.42%        |
| EvalPlus [27]                                | 67.52%  | 71.12%  | 11.56%    | 15.15%    | 0.1139   | 79.27%        |
| TCGCoder-7B (SAGA-distilled model)           | 85.14%  | 89.44%  | 17.93%    | 29.11%    | 0.1890   | 94.43%        |
| SAGA (DeepSeek-V3 Backbone)                  | 85.66%  | 90.62%  | 22.40%    | 32.58%    | 0.2228   | 94.06%        |
| SAGA Ablation Studies                        |         |         |           |           |          |               |
| Analytical Component Ablation                |         |         |           |           |          |               |
| SAGA w/ Multidim. Analysis only              | 84.51%  | 88.00%  | 20.70%    | 26.05%    | 0.1923   | 95.81%        |
| SAGA w/ Differential Analysis only           | 84.31%  | 88.16%  | 19.85%    | 26.67%    | 0.1926   | 94.41%        |
| Prompt Design Ablation                       |         |         |           |           |          |               |
| SimpleCOT Prompt for SAGA                    | 83.36%  | 84.54%  | 15.61%    | 19.11%    | 0.1424   | 96.23%        |
| Random Input w/ GT for SAGA                  | 82.31%  | 86.64%  | 16.44%    | 22.70%    | 0.1616   | 85.38%        |
| EvalPlus w/ GT for SAGA                      | 76.72%  | 79.56%  | 11.67%    | 20.44%    | 0.1278   | 89.49%        |
| Base LLM Ablation for SAGA                   |         |         |           |           |          |               |
| SAGA w/ Qwen2.5-Coder-7B-Instruct            | 78.88%  | 79.78%  | 19.70%    | 22.96%    | 0.1810   | 96.80%        |
| SAGA w/ Qwen2.5-72B-Instruct                 | 82.77%  | 85.08%  | 20.30%    | 26.46%    | 0.1943   | 94.92%        |
| SAGA w/ Qwen2.5-Coder-32B-Instruct           | 86.25%  | 90.54%  | 20.74%    | 32.73%    | 0.2139   | 94.72%        |

## DataFrame Info

Shape: (18, 7)
Columns: ['Method / Configuration', 'DR@20', 'DR@50', 'VAcc@20', 'VAcc@50', 'AUC@50', 'DivRatio@50']

### DataFrame Preview

|    | Method / Configuration                       | DR@20   | DR@50   | VAcc@20   | VAcc@50   | AUC@50   | DivRatio@50   |
|---:|:---------------------------------------------|:--------|:--------|:----------|:----------|:---------|:--------------|
|  0 | Main Comparison with Baseline TCG Methods    |         |         |           |           |          |               |
|  1 | TestChain [22]                               | 65.91%  | 68.31%  | 8.12%     | 11.88%    | 0.0841   | 50.09%        |
|  2 | Input-Interpreter (LiveCodeBench-style [19]) | 77.84%  | 81.07%  | 12.36%    | 16.72%    | 0.1234   | 79.42%        |
|  3 | EvalPlus [27]                                | 67.52%  | 71.12%  | 11.56%    | 15.15%    | 0.1139   | 79.27%        |
|  4 | TCGCoder-7B (SAGA-distilled model)           | 85.14%  | 89.44%  | 17.93%    | 29.11%    | 0.1890   | 94.43%        |
|  5 | SAGA (DeepSeek-V3 Backbone)                  | 85.66%  | 90.62%  | 22.40%    | 32.58%    | 0.2228   | 94.06%        |
|  6 | SAGA Ablation Studies                        |         |         |           |           |          |               |
|  7 | Analytical Component Ablation                |         |         |           |           |          |               |
|  8 | SAGA w/ Multidim. Analysis only              | 84.51%  | 88.00%  | 20.70%    | 26.05%    | 0.1923   | 95.81%        |
|  9 | SAGA w/ Differential Analysis only           | 84.31%  | 88.16%  | 19.85%    | 26.67%    | 0.1926   | 94.41%        |
