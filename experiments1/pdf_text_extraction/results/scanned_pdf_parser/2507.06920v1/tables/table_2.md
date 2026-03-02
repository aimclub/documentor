# Table 3

ID: 00000071
Page: 7
BBox: [208, 222, 1026, 590]

## Markdown Table



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
