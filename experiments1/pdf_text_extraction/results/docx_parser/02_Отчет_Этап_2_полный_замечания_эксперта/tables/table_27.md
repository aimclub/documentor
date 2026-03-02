# Table 27

ID: 00000260
Page: N/A
BBox: []

## Markdown Table

{
  "index": 26,
  "xml_position": 688,
  "rows": [
    {
      "row_index": 0,
      "cells": [
        {
          "cell_index": 0,
          "row": 0,
          "col": 0,
          "text": "Функции, обрабатывающие входящий запрос",
          "text_length": 39,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 0,
          "col": 1,
          "text": "Таблицы, в которые сохраняется информация о назначении сотрудника",
          "text_length": 65,
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
          "text": "addAssignment(NewEmployeeAssignmentRequest)",
          "text_length": 43,
          "is_merged": false,
          "colspan": 1,
          "rowspan": 1
        },
        {
          "cell_index": 1,
          "row": 1,
          "col": 1,
          "text": "assignments (назначение сотрудников)assignment_questions (назначенные вопросы теста)",
          "text_length": 84,
          "is_merged": true,
          "colspan": 1,
          "rowspan": 2
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
          "text": "newAssignment(NewEmployeeAssignmentDTO)",
          "text_length": 39,
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
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
        }
      ],
      "cells_count": 1
    },
    {
      "row_index": 3,
      "cells": [
        {
          "cell_index": 0,
          "row": 3,
          "col": 0,
          "text": "QuestionsAssignmentService::execute(array $employeeIds, string $knowledgeFieldId, Carbon $deadLine )",
          "text_length": 100,
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
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
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
          "text": "selectQuestions(array $questions, int $questionAmount )",
          "text_length": 55,
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
          "is_merged": true,
          "colspan": 1,
          "rowspan": 0
        }
      ],
      "cells_count": 1
    }
  ],
  "rows_count": 5,
  "cols_count": 2,
  "merged_cells": [
    {
      "row": 1,
      "col": 1,
      "colspan": 1,
      "rowspan": 2
    }
  ],
  "estimated_page": 14,
  "data": [
    [
      "Функции, обрабатывающие входящий запрос",
      "Таблицы, в которые сохраняется информация о назначении сотрудника"
    ],
    [
      "addAssignment(NewEmployeeAssignmentRequest)",
      "assignments (назначение сотрудников)assignment_questions (назначенные вопросы теста)"
    ],
    [
      "newAssignment(NewEmployeeAssignmentDTO)"
    ],
    [
      "QuestionsAssignmentService::execute(array $employeeIds, string $knowledgeFieldId, Carbon $deadLine )"
    ],
    [
      "selectQuestions(array $questions, int $questionAmount )"
    ]
  ],
  "captions": [
    {
      "text": "Таблица 14.2 - Функции, обрабатывающие входящий запрос на формирование теста с \nуказанием соответствующих таблиц в БД, куда сохраняется информация о запросе.",
      "table_number": 14,
      "bbox": [
        168,
        887,
        1122,
        958
      ],
      "page": 63,
      "type": "caption",
      "matched_from_xml": true
    }
  ]
}

## DataFrame Info

Shape: (5, 2)
Columns: ['Column_1', 'Column_2']

### DataFrame Preview

|    | Column_1                                                                                             | Column_2                                                                             |
|---:|:-----------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------|
|  0 | Функции, обрабатывающие входящий запрос                                                              | Таблицы, в которые сохраняется информация о назначении сотрудника                    |
|  1 | addAssignment(NewEmployeeAssignmentRequest)                                                          | assignments (назначение сотрудников)assignment_questions (назначенные вопросы теста) |
|  2 | newAssignment(NewEmployeeAssignmentDTO)                                                              |                                                                                      |
|  3 | QuestionsAssignmentService::execute(array $employeeIds, string $knowledgeFieldId, Carbon $deadLine ) |                                                                                      |
|  4 | selectQuestions(array $questions, int $questionAmount )                                              |                                                                                      |
