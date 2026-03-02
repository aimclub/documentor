# Table 23

ID: 00000231
Page: N/A
BBox: []

## Markdown Table

{
  "index": 22,
  "xml_position": 625,
  "rows": [
    {
      "row_index": 0,
      "cells": [
        {
          "cell_index": 0,
          "row": 0,
          "col": 0,
          "text": "Эндпоинт",
          "text_length": 8,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 0,
          "col": 1,
          "text": "Таблицы, в которые сохраняется информация",
          "text_length": 41,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 2
    },
    {
      "row_index": 1,
      "cells": [
        {
          "cell_index": 0,
          "row": 1,
          "col": 0,
          "text": "Route::get('/question-activity/{uuid}', [QuestionManageController::class, 'questionActivity']);",
          "text_length": 95,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 1,
          "col": 1,
          "text": "questions",
          "text_length": 9,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 2
    },
    {
      "row_index": 2,
      "cells": [
        {
          "cell_index": 0,
          "row": 2,
          "col": 0,
          "text": "Route::post('/question/{uuid}', [QuestionController::class, 'update']);",
          "text_length": 71,
          "is_merged": true,
          "colspan": 1,
          "rowspan": 2
        },
        {
          "cell_index": 1,
          "row": 2,
          "col": 1,
          "text": "questions",
          "text_length": 9,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 2
    },
    {
      "row_index": 3,
      "cells": [
        {
          "cell_index": 0,
          "row": 3,
          "col": 0,
          "text": "",
          "text_length": 0,
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
        },
        {
          "cell_index": 0,
          "row": 3,
          "col": 0,
          "text": "question_answers",
          "text_length": 16,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 1
    },
    {
      "row_index": 4,
      "cells": [
        {
          "cell_index": 0,
          "row": 4,
          "col": 0,
          "text": "",
          "text_length": 0,
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
        },
        {
          "cell_index": 0,
          "row": 4,
          "col": 0,
          "text": "question_reviews",
          "text_length": 16,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 1
    },
    {
      "row_index": 5,
      "cells": [
        {
          "cell_index": 0,
          "row": 5,
          "col": 0,
          "text": "",
          "text_length": 0,
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
        },
        {
          "cell_index": 0,
          "row": 5,
          "col": 0,
          "text": "question_answers_reviews",
          "text_length": 24,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        }
      ],
      "cells_count": 1
    }
  ],
  "rows_count": 6,
  "cols_count": 2,
  "merged_cells": [
    {
      "row": 2,
      "col": 0,
      "colspan": 1,
      "rowspan": 2
    }
  ],
  "estimated_page": 13,
  "data": [
    [
      "Эндпоинт",
      "Таблицы, в которые сохраняется информация"
    ],
    [
      "Route::get('/question-activity/{uuid}', [QuestionManageController::class, 'questionActivity']);",
      "questions"
    ],
    [
      "Route::post('/question/{uuid}', [QuestionController::class, 'update']);",
      "questions"
    ],
    [
      "question_answers"
    ],
    [
      "question_reviews"
    ],
    [
      "question_answers_reviews"
    ]
  ],
  "captions": [
    {
      "text": "Таблица 13.5 - Перечень эндпоинтов и таблиц, в которых сохраняется информация о \nвопросах после их валидации редактором и экспертом.",
      "table_number": 13,
      "bbox": [
        167,
        927,
        1123,
        1001
      ],
      "page": 58,
      "type": "caption",
      "matched_from_xml": true
    }
  ]
}

## DataFrame Info

Shape: (5, 2)
Columns: ['Эндпоинт', 'Таблицы, в которые сохраняется информация']

### DataFrame Preview

|    | Эндпоинт                                                                                        | Таблицы, в которые сохраняется информация   |
|---:|:------------------------------------------------------------------------------------------------|:--------------------------------------------|
|  0 | Route::get('/question-activity/{uuid}', [QuestionManageController::class, 'questionActivity']); | questions                                   |
|  1 | Route::post('/question/{uuid}', [QuestionController::class, 'update']);                         | questions                                   |
|  2 | question_answers                                                                                |                                             |
|  3 | question_reviews                                                                                |                                             |
|  4 | question_answers_reviews                                                                        |                                             |
