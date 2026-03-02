# Table 1

ID: 00000014
Page: N/A
BBox: []

## Markdown Table

{
  "index": 0,
  "xml_position": 53,
  "rows": [
    {
      "row_index": 0,
      "cells": [
        {
          "cell_index": 0,
          "row": 0,
          "col": 0,
          "text": "Обозначение",
          "text_length": 11,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 0,
          "col": 1,
          "text": "Формула (для одного изображения)",
          "text_length": 32,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 0,
          "col": 2,
          "text": "Пояснение",
          "text_length": 9,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    },
    {
      "row_index": 1,
      "cells": [
        {
          "cell_index": 0,
          "row": 1,
          "col": 0,
          "text": "IoU (Intersection-over-Union)",
          "text_length": 29,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 1,
          "col": 1,
          "text": "",
          "text_length": 0,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 1,
          "col": 2,
          "text": "Мера перекрытия, предсказанного Bounding-Box Bpred и эталонного Bgt",
          "text_length": 67,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    },
    {
      "row_index": 2,
      "cells": [
        {
          "cell_index": 0,
          "row": 2,
          "col": 0,
          "text": "Precision",
          "text_length": 9,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 2,
          "col": 1,
          "text": "",
          "text_length": 0,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 2,
          "col": 2,
          "text": "Доля предсказанных боксов, попавших в «правильные» (IoU ≥ τ).",
          "text_length": 61,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    },
    {
      "row_index": 3,
      "cells": [
        {
          "cell_index": 0,
          "row": 3,
          "col": 0,
          "text": "Recall",
          "text_length": 6,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 3,
          "col": 1,
          "text": "",
          "text_length": 0,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 3,
          "col": 2,
          "text": "Доля эталонных боксов, которые модель успешно нашла.",
          "text_length": 52,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    },
    {
      "row_index": 4,
      "cells": [
        {
          "cell_index": 0,
          "row": 4,
          "col": 0,
          "text": "F1@50",
          "text_length": 5,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 4,
          "col": 1,
          "text": "",
          "text_length": 0,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 4,
          "col": 2,
          "text": "Гармоническое среднее Precision и Recall при пороге IoU = 0.5.",
          "text_length": 62,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    }
  ],
  "rows_count": 5,
  "cols_count": 3,
  "merged_cells": [],
  "estimated_page": 2,
  "data": [
    [
      "Обозначение",
      "Формула (для одного изображения)",
      "Пояснение"
    ],
    [
      "IoU (Intersection-over-Union)",
      "",
      "Мера перекрытия, предсказанного Bounding-Box Bpred и эталонного Bgt"
    ],
    [
      "Precision",
      "",
      "Доля предсказанных боксов, попавших в «правильные» (IoU ≥ τ)."
    ],
    [
      "Recall",
      "",
      "Доля эталонных боксов, которые модель успешно нашла."
    ],
    [
      "F1@50",
      "",
      "Гармоническое среднее Precision и Recall при пороге IoU = 0.5."
    ]
  ],
  "captions": [
    {
      "text": "Таблица 1.1 — Основные метрики для оценки качества локализации",
      "table_number": 1,
      "bbox": [
        140,
        144,
        858,
        174
      ],
      "page": 5,
      "type": "caption",
      "matched_from_xml": true
    }
  ]
}

## DataFrame Info

Shape: (4, 3)
Columns: ['Обозначение', 'Формула (для одного изображения)', 'Пояснение']

### DataFrame Preview

|    | Обозначение                   | Формула (для одного изображения)   | Пояснение                                                           |
|---:|:------------------------------|:-----------------------------------|:--------------------------------------------------------------------|
|  0 | IoU (Intersection-over-Union) |                                    | Мера перекрытия, предсказанного Bounding-Box Bpred и эталонного Bgt |
|  1 | Precision                     |                                    | Доля предсказанных боксов, попавших в «правильные» (IoU ≥ τ).       |
|  2 | Recall                        |                                    | Доля эталонных боксов, которые модель успешно нашла.                |
|  3 | F1@50                         |                                    | Гармоническое среднее Precision и Recall при пороге IoU = 0.5.      |
