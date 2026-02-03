# Реализация PdfParser

## Архитектура PdfParser

```mermaid
graph TB
    Start([LangChain Document<br/>PDF файл]) --> PdfParser[PdfParser<br/>BaseParser]
    
    PdfParser --> TextDetector[Определение типа PDF<br/>is_text_extractable]
    
    TextDetector -->|Текст выделяется| TextPath[Путь 1: Извлекаемый текст]
    TextDetector -->|Текст не выделяется| OCRPath[Путь 2: OCR пайплайн]
    
    TextPath --> PdfPlumber[PdfPlumber<br/>Извлечение текста и структуры]
    
    PdfPlumber -->|Текст по страницам| TextExtractor[Извлечение текста<br/>базовая структура]
    
    TextExtractor -->|Текст с перекрытием| LLMChunker[Разбиение на чанки<br/>с перекрытием]
    
    LLMChunker -->|Чанки ~3000 символов| LLMHeaderDetector[LLM детектирование заголовков<br/>Qwen или другая модель]
    
    LLMHeaderDetector -->|Заголовки и уровни| HeaderStructure[Структура заголовков<br/>с уровнями]
    
    HeaderStructure -->|Построение иерархии| TextHierarchy[Иерархия элементов<br/>parent_id]
    
    OCRPath --> PageRenderer[Рендеринг страниц<br/>в изображения]
    
    PageRenderer -->|Изображения страниц| LayoutDetector[Dots.OCR Layout Detection<br/>Определение структуры страницы]
    
    LayoutDetector -->|Layout элементы| LayoutElements[Элементы layout:<br/>Text, Picture, Caption,<br/>Table, Section-header и т.д.]
    
    LayoutElements -->|Порядок чтения| ReadingOrder[Построение порядка чтения<br/>reading order]
    
    ReadingOrder -->|Координаты текстовых блоков| TextExtractor[PyMuPDF<br/>Извлечение текста по координатам]
    
    TextExtractor -->|Текст из PDF<br/>с координатами| OCRText[Текст из PyMuPDF<br/>с координатами из Dots.OCR]
    
    OCRText -->|Структурирование| OCRStructure[Структурирование<br/>по layout типам]
    
    Note1[Dots.OCR: только layout detection<br/>PyMuPDF: извлечение текста<br/>OCR LLM: НЕ используется]
    
    OCRStructure -->|Построение иерархии| OCRHierarchy[Иерархия элементов<br/>parent_id]
    
    TextHierarchy --> ElementCreator[Создание Element<br/>с id, type, content,<br/>parent_id, metadata]
    
    OCRHierarchy --> ElementCreator
    
    ElementCreator -->|Использует| IdGenerator[ElementIdGenerator<br/>next_id]
    
    ElementCreator --> ElementsList[Список Element]
    
    ElementsList --> ParsedDoc[ParsedDocument<br/>source, format, elements]
    
    ParsedDoc --> Output([Результат:<br/>Структурированные элементы])
    
    style Start fill:#e1f5ff
    style PdfParser fill:#fff4e1
    style TextDetector fill:#e8f5e9
    style TextPath fill:#c8e6c9
    style OCRPath fill:#ffccbc
    style PdfPlumber fill:#e3f2fd
    style LLMHeaderDetector fill:#f3e5f5
    style LayoutDetector fill:#fff9c4
    style OCRProcessor fill:#f3e5f5
    style ElementCreator fill:#e3f2fd
    style ParsedDoc fill:#fff9c4
    style Output fill:#c8e6c9
```

## Путь 1: Извлекаемый текст (PdfPlumber + LLM)

```mermaid
sequenceDiagram
    participant Parser as PdfParser
    participant Detector as TextDetector
    participant Plumber as PdfPlumber
    participant Chunker as LLMChunker
    participant LLM as LLM Header Detector
    participant Hierarchy as Hierarchy Builder
    
    Parser->>Detector: is_text_extractable(pdf)
    Detector-->>Parser: True (текст выделяется)
    
    Parser->>Plumber: extract_text_and_structure(pdf)
    Plumber->>Plumber: Открыть PDF
    Plumber->>Plumber: Извлечь текст по страницам
    Plumber->>Plumber: Базовая структура (абзацы, таблицы)
    Plumber-->>Parser: Текст с метаданными
    
    Parser->>Chunker: split_with_overlap(text, chunk_size=3000, overlap=1_paragraph)
    Chunker->>Chunker: Разбить на чанки
    Chunker-->>Parser: Список чанков с перекрытием
    
    loop Для каждого чанка
        Parser->>LLM: detect_headers(chunk, previous_headers)
        Note over LLM: Определить заголовки, уровни,<br/>проверить логику иерархии
        LLM-->>Parser: Список заголовков с уровнями
    end
    
    Parser->>Hierarchy: build_hierarchy(text, headers)
    Hierarchy->>Hierarchy: Назначить parent_id
    Hierarchy->>Hierarchy: Построить дерево элементов
    Hierarchy-->>Parser: Список Element с иерархией
    
    Parser->>Parser: Создать ParsedDocument
```

## Путь 2: OCR пайплайн (Dots.OCR layout + PyMuPDF text extraction)

**Важно**: Dots.OCR используется ТОЛЬКО для определения layout и координат блоков. Текст извлекается через PyMuPDF по координатам из Dots.OCR. OCR LLM (Qwen OCR) НЕ используется, если текст доступен в PDF.

```mermaid
sequenceDiagram
    participant Parser as PdfParser
    participant Renderer as PageRenderer
    participant Layout as Dots.OCR Layout
    participant ReadingOrder as Reading Order Builder
    participant PyMuPDF as PyMuPDF Text Extractor
    participant Structure as Structure Builder
    
    Parser->>Renderer: render_pages_to_images(pdf)
    Renderer->>Renderer: Конвертировать страницы в изображения
    Renderer-->>Parser: Список изображений страниц
    
    loop Для каждой страницы
        Parser->>Layout: detect_layout(page_image)
        Layout->>Layout: Определить типы элементов и координаты
        Layout-->>Parser: Layout элементы с bbox:<br/>Text, Picture, Caption,<br/>Table, Section-header и т.д.
        
        Parser->>ReadingOrder: build_reading_order(layout_elements)
        ReadingOrder->>ReadingOrder: Определить порядок чтения
        ReadingOrder->>ReadingOrder: Сгруппировать элементы
        ReadingOrder-->>Parser: Упорядоченные элементы с координатами
        
        loop Для текстовых блоков
            Parser->>PyMuPDF: extract_text_by_bbox(pdf, bbox)
            Note over PyMuPDF: Извлечение текста из PDF<br/>по координатам из Dots.OCR
            PyMuPDF-->>Parser: Текст из PDF + координаты
        end
    end
    
    Parser->>Structure: structure_elements(layout, pdf_text)
    Structure->>Structure: Сопоставить layout типы с текстом
    Structure->>Structure: Построить иерархию
    Structure-->>Parser: Список Element с иерархией
    
    Parser->>Parser: Создать ParsedDocument
```

## Детальная структура OCR пайплайна

```mermaid
graph TB
    PDF[PDF файл] --> Render[Рендеринг страниц]
    
    Render -->|Страница 1| Page1[Изображение страницы 1]
    Render -->|Страница 2| Page2[Изображение страницы 2]
    Render -->|Страница N| PageN[Изображение страницы N]
    
    Page1 --> Layout1[Dots.OCR Layout Detection]
    Page2 --> Layout2[Dots.OCR Layout Detection]
    PageN --> LayoutN[Dots.OCR Layout Detection]
    
    Layout1 -->|Layout элементы| Elements1[Элементы страницы 1:<br/>- Text bbox<br/>- Picture bbox<br/>- Caption bbox<br/>- Table bbox<br/>- Section-header bbox]
    
    Layout2 -->|Layout элементы| Elements2[Элементы страницы 2]
    LayoutN -->|Layout элементы| ElementsN[Элементы страницы N]
    
    Elements1 --> ReadingOrder[Построение порядка чтения<br/>по координатам и типам]
    Elements2 --> ReadingOrder
    ElementsN --> ReadingOrder
    
    ReadingOrder -->|Упорядоченные зоны<br/>с координатами| TextZones[Текстовые блоки<br/>с bbox из Dots.OCR]
    
    TextZones -->|Для каждого текстового блока| PyMuPDFExtract[PyMuPDF<br/>Извлечение текста по bbox]
    
    Note over PyMuPDFExtract: Dots.OCR: только координаты<br/>PyMuPDF: извлечение текста<br/>OCR LLM: НЕ используется
    
    PyMuPDFExtract -->|Текст из PDF| OCRResults[Результаты:<br/>текст из PyMuPDF + bbox + page_num]
    
    OCRResults --> StructureBuilder[Структурирование элементов]
    
    StructureBuilder -->|По layout типам| TypeMapping[Маппинг типов:<br/>Section-header → HEADER_N<br/>Text → PLAIN_TEXT<br/>Picture → IMAGE<br/>Caption → CAPTION<br/>Table → TABLE]
    
    TypeMapping -->|С построением иерархии| HierarchyBuilder[Построение иерархии<br/>parent_id по уровням заголовков]
    
    HierarchyBuilder --> Elements[Список Element<br/>с полной структурой]
    
    style PDF fill:#e1f5ff
    style Layout1 fill:#fff4e1
    style ReadingOrder fill:#e8f5e9
    style PyMuPDFExtract fill:#e3f2fd
    style StructureBuilder fill:#e3f2fd
    style Elements fill:#c8e6c9
```

## LLM детектирование заголовков с перекрытием

```mermaid
graph TB
    Text[Текст из PdfPlumber] --> Chunker[Разбиение на чанки<br/>chunk_size: ~3000 символов<br/>overlap: 1 параграф]
    
    Chunker -->|Чанк 1| Chunk1[Чанк 1<br/>с перекрытием]
    Chunker -->|Чанк 2| Chunk2[Чанк 2<br/>с перекрытием]
    Chunker -->|Чанк N| ChunkN[Чанк N<br/>с перекрытием]
    
    Chunk1 -->|Первый запрос| LLM1[LLM запрос 1:<br/>Определить заголовки<br/>и их уровни]
    
    LLM1 -->|Заголовки| Headers1[Заголовки чанка 1:<br/>- HEADER_1: Заголовок 1<br/>- HEADER_2: Подзаголовок 1.1]
    
    Headers1 -->|Передать контекст| Chunk2Context[Чанк 2 + предыдущие заголовки]
    
    Chunk2Context -->|Следующий запрос| LLM2[LLM запрос 2:<br/>Определить новые заголовки<br/>с учётом существующих]
    
    LLM2 -->|Проверка логики| LogicCheck[Проверка логики:<br/>внутри HEADER_2<br/>не может быть HEADER_1]
    
    LogicCheck -->|Корректные заголовки| Headers2[Заголовки чанка 2:<br/>- HEADER_2: Подзаголовок 1.2<br/>- HEADER_3: Подподзаголовок]
    
    Headers2 -->|Передать контекст| ChunkNContext[Чанк N + все предыдущие заголовки]
    
    ChunkNContext -->|Последний запрос| LLMN[LLM запрос N:<br/>Определить заголовки<br/>с полным контекстом]
    
    LLMN -->|Финальные заголовки| HeadersN[Заголовки чанка N]
    
    Headers1 --> Merge[Объединение всех заголовков]
    Headers2 --> Merge
    HeadersN --> Merge
    
    Merge -->|Полная структура| HeaderTree[Дерево заголовков<br/>с уровнями и связями]
    
    HeaderTree -->|Применить к тексту| TextHierarchy[Иерархия текста<br/>с parent_id]
    
    style Text fill:#e1f5ff
    style Chunker fill:#fff4e1
    style LLM1 fill:#f3e5f5
    style LogicCheck fill:#e8f5e9
    style HeaderTree fill:#e3f2fd
    style TextHierarchy fill:#c8e6c9
```

## Маппинг типов Layout → ElementType

```mermaid
graph LR
    LayoutTypes[LayoutTypeDotsOCR] --> Mapping[Маппинг типов]
    
    Mapping -->|SECTION_HEADER| HeaderMapping[Определить уровень<br/>HEADER_1-6]
    Mapping -->|TEXT| PlainTextMapping[PLAIN_TEXT]
    Mapping -->|PICTURE| ImageMapping[IMAGE]
    Mapping -->|CAPTION| CaptionMapping[CAPTION]
    Mapping -->|TABLE| TableMapping[TABLE]
    Mapping -->|FORMULA| FormulaMapping[FORMULA]
    Mapping -->|TITLE| TitleMapping[DOCUMENT_TITLE<br/>или HEADER_1]
    Mapping -->|LIST_ITEM| ListMapping[LIST_ITEM]
    Mapping -->|PAGE_HEADER| SkipMapping[Пропустить<br/>или PAGE_BREAK]
    Mapping -->|PAGE_FOOTER| SkipMapping
    Mapping -->|FOOTNOTE| FootnoteMapping[QUOTE<br/>или PLAIN_TEXT]
    Mapping -->|OTHER| OtherMapping[PLAIN_TEXT]
    Mapping -->|UNKNOWN| UnknownMapping[PLAIN_TEXT]
    
    HeaderMapping --> Elements[Element с типом]
    PlainTextMapping --> Elements
    ImageMapping --> Elements
    CaptionMapping --> Elements
    TableMapping --> Elements
    FormulaMapping --> Elements
    TitleMapping --> Elements
    ListMapping --> Elements
    FootnoteMapping --> Elements
    OtherMapping --> Elements
    UnknownMapping --> Elements
    
    style LayoutTypes fill:#e1f5ff
    style Mapping fill:#fff4e1
    style Elements fill:#c8e6c9
```

## Классовая структура PdfParser

```mermaid
classDiagram
    class BaseParser {
        <<abstract>>
        +DocumentFormat format
        +ElementIdGenerator id_generator
        +can_parse(Document) bool
        +parse(Document)* ParsedDocument
    }
    
    class PdfParser {
        +parse(Document) ParsedDocument
        -_is_text_extractable(Document) bool
        -_parse_with_text_extraction(Document) ParsedDocument
        -_parse_with_ocr(Document) ParsedDocument
    }
    
    class PdfPlumberExtractor {
        +extract_text_and_structure(str) dict
        +get_pages(str) List~Page~
        +extract_tables(Page) List~Table~
    }
    
    class LLMHeaderDetector {
        +detect_headers(str, List~Header~) List~Header~
        +validate_hierarchy(List~Header~) bool
        -_call_llm(str, str) dict
    }
    
    class PageRenderer {
        +render_pages_to_images(str) List~Image~
        +render_page(int) Image
    }
    
    class LayoutDetector {
        +detect_layout(Image) List~LayoutElement~
        +get_reading_order(List~LayoutElement~) List~LayoutElement~
    }
    
    class PyMuPDFTextExtractor {
        +extract_text_by_bbox(str, bbox) str
        +extract_text_by_page(int) str
    }
    
    class LayoutTypeDotsOCR {
        <<enumeration>>
        TEXT
        PICTURE
        CAPTION
        SECTION_HEADER
        TABLE
        FORMULA
        TITLE
        ...
    }
    
    class Element {
        +str id
        +ElementType type
        +str content
        +str parent_id
        +dict metadata
    }
    
    BaseParser <|-- PdfParser
    PdfParser --> PdfPlumberExtractor : использует для текста
    PdfParser --> LLMHeaderDetector : использует для заголовков
    PdfParser --> PageRenderer : использует для layout detection
    PdfParser --> LayoutDetector : использует для layout
    PdfParser --> PyMuPDFTextExtractor : использует для извлечения текста
    LayoutDetector --> LayoutTypeDotsOCR : возвращает типы
    PdfParser --> Element : создаёт
```

## Процесс принятия решения: текст или OCR

```mermaid
graph TB
    PDF[PDF файл] --> CheckText{Проверка:<br/>is_text_extractable}
    
    CheckText -->|Попытка извлечь текст| TryExtract[Попытка извлечения<br/>pdfplumber.extract_text]
    
    TryExtract -->|Текст извлечён| CheckQuality{Качество текста<br/>достаточное?}
    
    CheckQuality -->|Да, текст хороший| UseTextPath[Использовать путь 1:<br/>PdfPlumber + LLM]
    
    CheckQuality -->|Нет, текст плохой| UseOCRPath[Использовать путь 2:<br/>OCR пайплайн]
    
    TryExtract -->|Текст не извлечён| UseOCRPath
    
    CheckText -->|Известно заранее:<br/>сканированный документ| UseOCRPath
    
    UseTextPath --> TextProcessing[Обработка текста]
    UseOCRPath --> OCRProcessing[Обработка OCR]
    
    TextProcessing --> Result[ParsedDocument]
    OCRProcessing --> Result
    
    style PDF fill:#e1f5ff
    style CheckText fill:#fff4e1
    style UseTextPath fill:#c8e6c9
    style UseOCRPath fill:#ffccbc
    style Result fill:#fff9c4
```
