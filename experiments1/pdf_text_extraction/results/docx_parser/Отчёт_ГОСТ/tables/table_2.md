# Table 2

ID: 00000016
Page: N/A
BBox: []

## Markdown Table

{
  "index": 1,
  "xml_position": 56,
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
          "text": "Формула",
          "text_length": 7,
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
          "text": "CER (Character Error Rate)",
          "text_length": 26,
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
          "text": "S — число заменённых символов, D — удалений, I — вставок; N — длина эталонной строки в символах",
          "text_length": 95,
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
          "text": "WER (Word Error Rate)",
          "text_length": 21,
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
          "text": "Аналог CER на уровне слов.",
          "text_length": 26,
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
          "text": "CERnorm / WERnorm",
          "text_length": 17,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 3,
          "col": 1,
          "text": "CER/WER после нормализации строки (нижний регистр, без пунктуации и лишних пробелов).",
          "text_length": 85,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 3,
          "col": 2,
          "text": "Применяют, когда регистр и пунктуация несущественны для downstream-задачи.",
          "text_length": 74,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 3
    }
  ],
  "rows_count": 4,
  "cols_count": 3,
  "merged_cells": [],
  "estimated_page": 2,
  "data": [
    [
      "Обозначение",
      "Формула",
      "Пояснение"
    ],
    [
      "CER (Character Error Rate)",
      "",
      "S — число заменённых символов, D — удалений, I — вставок; N — длина эталонной строки в символах"
    ],
    [
      "WER (Word Error Rate)",
      "",
      "Аналог CER на уровне слов."
    ],
    [
      "CERnorm / WERnorm",
      "CER/WER после нормализации строки (нижний регистр, без пунктуации и лишних пробелов).",
      "Применяют, когда регистр и пунктуация несущественны для downstream-задачи."
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

Shape: (3, 3)
Columns: ['Обозначение', 'Формула', 'Пояснение']

### DataFrame Preview

|    | Обозначение                | Формула                                                                               | Пояснение                                                                                       |
|---:|:---------------------------|:--------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------|
|  0 | CER (Character Error Rate) |                                                                                       | S — число заменённых символов, D — удалений, I — вставок; N — длина эталонной строки в символах |
|  1 | WER (Word Error Rate)      |                                                                                       | Аналог CER на уровне слов.                                                                      |
|  2 | CERnorm / WERnorm          | CER/WER после нормализации строки (нижний регистр, без пунктуации и лишних пробелов). | Применяют, когда регистр и пунктуация несущественны для downstream-задачи.                      |
