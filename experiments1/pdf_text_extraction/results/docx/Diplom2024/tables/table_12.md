# Table 12

ID: 00000039
Page: N/A
BBox: []

## Markdown Table

{
  "index": 11,
  "xml_position": 67,
  "rows": [
    {
      "row_index": 0,
      "cells": [
        {
          "cell_index": 0,
          "row": 0,
          "col": 0,
          "text": "Название атрибута",
          "text_length": 17,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 0,
          "col": 1,
          "text": "Домен",
          "text_length": 5,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 0,
          "col": 2,
          "text": "Ключ",
          "text_length": 4,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 3,
          "row": 0,
          "col": 3,
          "text": "Описание",
          "text_length": 8,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 4
    },
    {
      "row_index": 1,
      "cells": [
        {
          "cell_index": 0,
          "row": 1,
          "col": 0,
          "text": "idContainsSkill",
          "text_length": 15,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 1,
          "col": 1,
          "text": "int",
          "text_length": 3,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 1,
          "col": 2,
          "text": "PK",
          "text_length": 2,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 3,
          "row": 1,
          "col": 3,
          "text": "Идентификатор",
          "text_length": 13,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 4
    },
    {
      "row_index": 2,
      "cells": [
        {
          "cell_index": 0,
          "row": 2,
          "col": 0,
          "text": "idLaborFunc",
          "text_length": 11,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 2,
          "col": 1,
          "text": "int",
          "text_length": 3,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 2,
          "col": 2,
          "text": "FK(tblLa- borFunc)",
          "text_length": 18,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 3,
          "row": 2,
          "col": 3,
          "text": "Идентификатор трудовой функции",
          "text_length": 30,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 4
    },
    {
      "row_index": 3,
      "cells": [
        {
          "cell_index": 0,
          "row": 3,
          "col": 0,
          "text": "idNecSkill",
          "text_length": 10,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 3,
          "col": 1,
          "text": "int",
          "text_length": 3,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 2,
          "row": 3,
          "col": 2,
          "text": "FK(tblNe- cessarySkill)",
          "text_length": 23,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 3,
          "row": 3,
          "col": 3,
          "text": "Идентификатор необходимого умения",
          "text_length": 33,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 4
    }
  ],
  "rows_count": 4,
  "cols_count": 4,
  "merged_cells": [],
  "estimated_page": 2,
  "data": [
    [
      "Название атрибута",
      "Домен",
      "Ключ",
      "Описание"
    ],
    [
      "idContainsSkill",
      "int",
      "PK",
      "Идентификатор"
    ],
    [
      "idLaborFunc",
      "int",
      "FK(tblLa- borFunc)",
      "Идентификатор трудовой функции"
    ],
    [
      "idNecSkill",
      "int",
      "FK(tblNe- cessarySkill)",
      "Идентификатор необходимого умения"
    ]
  ],
  "captions": [
    {
      "text": "Таблица 11: tblLaborFuncContainsKnowledge",
      "table_number": 11,
      "bbox": [
        388,
        312,
        930,
        347
      ],
      "page": 9,
      "type": "caption",
      "matched_from_xml": true
    }
  ]
}

## DataFrame Info

Shape: (3, 4)
Columns: ['Название атрибута', 'Домен', 'Ключ', 'Описание']

### DataFrame Preview

|    | Название атрибута   | Домен   | Ключ                    | Описание                          |
|---:|:--------------------|:--------|:------------------------|:----------------------------------|
|  0 | idContainsSkill     | int     | PK                      | Идентификатор                     |
|  1 | idLaborFunc         | int     | FK(tblLa- borFunc)      | Идентификатор трудовой функции    |
|  2 | idNecSkill          | int     | FK(tblNe- cessarySkill) | Идентификатор необходимого умения |
