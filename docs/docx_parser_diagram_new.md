# Реализация DocxParser

## Архитектура DocxParser

```mermaid
graph TB
    Start([LangChain Document<br/>DOCX файл]) --> DocxParser[DocxParser<br/>BaseParser]
    
    DocxParser --> DocxExtractor[Извлечение текста и метаданных<br/>из DOCX<br/>python-docx или аналог]
    
    DocxExtractor -->|Текст + стили + метаданные| TextChunker[Разбиение на чанки<br/>~3000 символов<br/>перекрытие: 1 параграф]
    
    TextChunker -->|Чанки с перекрытием| LLMText[LLM семантический анализ<br/>Qwen или другая модель]
    
    LLMText -->|Запрос к LLM| LLMTextRequest[LLM запрос:<br/>- Найти заголовки по смыслу<br/>- Определить уровни<br/>- Классифицировать элементы<br/>- Выстроить иерархию]
    
    LLMTextRequest -->|Предварительная структура| TextStructure[Структура из семантического анализа]
    
    TextStructure -->|Проверка и корректировка| Strategy{Выбор стратегии<br/>проверки разметки}
    
    Strategy -->|Вариант 1| BuiltInMarkup[Проверка через встроенные стили<br/>Heading 1, Heading 2 и т.д.]
    
    Strategy -->|Вариант 2| LLMXMLCheck[Проверка через LLM<br/>с XML разметкой DOCX]
    
    BuiltInMarkup -->|Стили из DOCX| StyleParser[Парсинг стилей:<br/>- Heading 1 → HEADER_1<br/>- Heading 2 → HEADER_2<br/>- Title → DOCUMENT_TITLE<br/>- Обычный текст → PLAIN_TEXT]
    
    StyleParser -->|Сравнение и корректировка| StyleCorrection[Корректировка структуры:<br/>сравнение LLM результата<br/>со встроенными стилями]
    
    LLMXMLCheck -->|XML разметка DOCX| XMLParser[Извлечение XML разметки<br/>стилей и структуры]
    
    XMLParser -->|XML + LLM структура| LLMXMLRequest[LLM запрос:<br/>- Проверить свою разметку<br/>- Сравнить с XML<br/>- Скорректировать уровни]
    
    LLMXMLRequest -->|Скорректированная структура| XMLCorrection[Корректировка структуры<br/>на основе XML разметки]
    
    StyleCorrection -->|Финальная структура| FinalStructure[Финальная структура<br/>после проверки]
    
    XMLCorrection -->|Финальная структура| FinalStructure
    
    FinalStructure -->|Извлечение структурных элементов| StructuralElements[Структурные элементы:<br/>изображения, таблицы, формулы]
    
    StructuralElements --> ImageProcessor[Обработка изображений]
    StructuralElements --> TableProcessor[Обработка таблиц]
    StructuralElements --> FormulaProcessor[Обработка формул]
    
    ImageProcessor -->|Решение проблемы порядка| ImageOrderFixer[Исправление порядка изображений]
    
    ImageOrderFixer -->|Сопоставление| ImageMatcher[Сопоставление изображений:<br/>- По странице визуально<br/>- По контексту подписи<br/>- LLM сравнение]
    
    TableProcessor -->|Извлечение структуры| TableExtractor[Экспорт таблиц:<br/>HTML/Markdown<br/>объединённые ячейки]
    
    FormulaProcessor -->|Извлечение формул| FormulaExtractor[Формулы:<br/>OMML/MathML<br/>или распознавание по изображению]
    
    FinalStructure --> LinkResolver[Разрешение ссылок<br/>на структурные элементы]
    
    LinkResolver -->|Регулярные выражения| RegexLinker[Поиск ссылок:<br/>см. рис. 1, см. табл. 2]
    
    RegexLinker -->|LLM для сложных случаев| LLMLinker[LLM для определения<br/>ссылок на элементы]
    
    ImageMatcher --> ElementCreator[Создание Element<br/>с id, type, content,<br/>parent_id, metadata]
    TableExtractor --> ElementCreator
    FormulaExtractor --> ElementCreator
    LLMLinker --> ElementCreator
    
    ElementCreator -->|Использует| IdGenerator[ElementIdGenerator<br/>next_id]
    
    ElementCreator --> ElementsList[Список Element<br/>с полной структурой]
    
    ElementsList --> ParsedDoc[ParsedDocument<br/>source, format, elements]
    
    ParsedDoc --> Output([Результат:<br/>Структурированные элементы])
    
    style Start fill:#e1f5ff
    style DocxParser fill:#fff4e1
    style Strategy fill:#e8f5e9
    style BuiltInMarkup fill:#c8e6c9
    style LLMXMLCheck fill:#fff9c4
    style FinalStructure fill:#e3f2fd
    style ImageOrderFixer fill:#f3e5f5
    style ElementCreator fill:#e3f2fd
    style ParsedDoc fill:#fff9c4
    style Output fill:#c8e6c9
```

## Вариант 1: LLM семантика → Проверка через встроенные стили

```mermaid
sequenceDiagram
    participant Parser as DocxParser
    participant Extractor as DocxExtractor
    participant Chunker as TextChunker
    participant LLM as LLM Semantic
    participant StyleParser as Style Parser
    participant Corrector as Structure Corrector
    participant Hierarchy as Hierarchy Builder
    participant Elements as Structural Elements Processor
    
    Parser->>Extractor: extract_text_and_styles(docx_path)
    Extractor->>Extractor: python-docx извлечение
    Extractor->>Extractor: Извлечь текст по параграфам
    Extractor->>Extractor: Извлечь стили (Heading 1-6, Title и т.д.)
    Extractor-->>Parser: Текст + стили + метаданные
    
    Parser->>Chunker: split_with_overlap(text, chunk_size=3000, overlap=1_paragraph)
    Chunker-->>Parser: Список чанков
    
    loop Для каждого чанка
        Parser->>LLM: detect_headers_by_semantics(chunk, previous_headers)
        LLM-->>Parser: Предварительная структура чанка
    end
    
    Parser->>Parser: Объединить структуру из всех чанков
    Parser-->>Parser: Предварительная структура от LLM
    
    Parser->>StyleParser: parse_styles(paragraphs_with_styles)
    StyleParser->>StyleParser: Маппинг стилей:<br/>Heading 1 → HEADER_1<br/>Heading 2 → HEADER_2<br/>Title → DOCUMENT_TITLE
    StyleParser-->>Parser: Структура из встроенных стилей
    
    Parser->>Corrector: correct_structure(llm_structure, style_structure)
    Corrector->>Corrector: Сравнить LLM структуру со стилями
    Corrector->>Corrector: Скорректировать уровни заголовков
    Corrector->>Corrector: Исправить несоответствия
    Corrector-->>Parser: Скорректированная структура
    
    Parser->>Hierarchy: build_hierarchy(corrected_structure)
    Hierarchy->>Hierarchy: Назначить parent_id на основе уровней заголовков
    Hierarchy-->>Parser: Иерархия элементов
    
    Parser->>Elements: extract_structural_elements(docx)
    Elements-->>Parser: Изображения, таблицы, формулы
    
    Parser->>Parser: Объединить скорректированную структуру<br/>со структурными элементами
    Parser->>Parser: Создать ParsedDocument
```

## Вариант 2: LLM семантика → Проверка через LLM с XML разметкой

```mermaid
sequenceDiagram
    participant Parser as DocxParser
    participant Extractor as DocxExtractor
    participant Chunker as TextChunker
    participant LLM1 as LLM Semantic
    participant XMLParser as XML Parser
    participant LLM2 as LLM Validator
    participant Corrector as Structure Corrector
    participant Hierarchy as Hierarchy Builder
    participant Elements as Structural Elements Processor
    
    Parser->>Extractor: extract_text_and_xml(docx_path)
    Extractor->>Extractor: python-docx извлечение
    Extractor->>Extractor: Извлечь текст по параграфам
    Extractor->>Extractor: Извлечь XML разметку (стили, структура)
    Extractor-->>Parser: Текст + XML разметка + метаданные
    
    Parser->>Chunker: split_with_overlap(text, chunk_size=3000, overlap=1_paragraph)
    Chunker-->>Parser: Список чанков
    
    loop Для каждого чанка
        Parser->>LLM1: detect_headers_by_semantics(chunk, previous_headers)
        LLM1-->>Parser: Предварительная структура чанка
    end
    
    Parser->>Parser: Объединить структуру из всех чанков
    Parser-->>Parser: Предварительная структура от LLM
    
    Parser->>XMLParser: parse_xml_markup(xml_content)
    XMLParser->>XMLParser: Извлечь стили из XML
    XMLParser->>XMLParser: Извлечь структуру документа
    XMLParser-->>Parser: XML структура (стили, уровни заголовков)
    
    Parser->>LLM2: validate_structure_with_xml(llm_structure, xml_structure)
    Note over LLM2: LLM запрос:<br/>- Проверить свою разметку<br/>- Сравнить с XML разметкой<br/>- Скорректировать уровни<br/>- Исправить несоответствия
    LLM2-->>Parser: Скорректированная структура
    
    Parser->>Corrector: apply_corrections(llm_structure, llm_corrections)
    Corrector->>Corrector: Применить корректировки от LLM
    Corrector-->>Parser: Финальная скорректированная структура
    
    Parser->>Hierarchy: build_hierarchy(corrected_structure)
    Hierarchy->>Hierarchy: Назначить parent_id на основе уровней заголовков
    Hierarchy-->>Parser: Иерархия элементов
    
    Parser->>Elements: extract_structural_elements(docx)
    Elements-->>Parser: Изображения, таблицы, формулы
    
    Parser->>Parser: Объединить скорректированную структуру<br/>со структурными элементами
    Parser->>Parser: Создать ParsedDocument
```

## Проблема порядка изображений и решение

```mermaid
graph TB
    Docx[DOCX файл] --> Extract[Извлечение изображений]
    
    Extract -->|Порядок в DOCX XML| DocxOrder[Изображения в порядке XML:<br/>рис. 3, рис. 1, рис. 2]
    
    Extract -->|Визуальный порядок| VisualOrder[Визуальный порядок:<br/>рис. 1, рис. 2, рис. 3]
    
    DocxOrder -->|Проблема| Mismatch[Несоответствие порядка]
    VisualOrder -->|Ожидаемый| Expected[Ожидаемый порядок]
    
    Mismatch --> Solution{Решение проблемы}
    
    Solution -->|Вариант 1| PageBased[Сопоставление по странице<br/>рендеринг страницы<br/>определение позиции]
    
    Solution -->|Вариант 2| ContextBased[Сопоставление по контексту<br/>анализ текста вокруг подписи<br/>поиск упоминаний]
    
    Solution -->|Вариант 3| LLMCompare[LLM сравнение изображений<br/>это одинаковые картинки или нет?]
    
    PageBased -->|Координаты на странице| PositionMatch[Сопоставление по позиции<br/>bbox координаты]
    
    ContextBased -->|Текст вокруг| TextMatch[Сопоставление по тексту<br/>подпись + контекст]
    
    LLMCompare -->|Визуальное сравнение| VisualMatch[Сопоставление визуально<br/>LLM определяет идентичность]
    
    PositionMatch -->|Объединение результатов| FinalMatch[Финальное сопоставление<br/>правильный порядок]
    TextMatch -->|Объединение результатов| FinalMatch
    VisualMatch -->|Объединение результатов| FinalMatch
    
    FinalMatch -->|Правильный порядок| CorrectOrder[Изображения в правильном порядке:<br/>рис. 1 → изображение 1<br/>рис. 2 → изображение 2<br/>рис. 3 → изображение 3]
    
    CorrectOrder -->|Привязка подписей| CaptionLink[Подпись → Изображение<br/>корректная привязка]
    
    style Docx fill:#e1f5ff
    style Mismatch fill:#ffcdd2
    style Solution fill:#fff4e1
    style FinalMatch fill:#e8f5e9
    style CorrectOrder fill:#c8e6c9
```

## Обработка структурных элементов

```mermaid
graph TB
    Docx[DOCX файл] --> StructuralExtractor[Извлечение структурных элементов]
    
    StructuralExtractor -->|Изображения| ImageExtractor[Извлечение изображений]
    StructuralExtractor -->|Таблицы| TableExtractor[Извлечение таблиц]
    StructuralExtractor -->|Формулы| FormulaExtractor[Извлечение формул]
    
    ImageExtractor -->|Изображения + подписи| ImageProcessor[Обработка изображений]
    
    ImageProcessor -->|Проблема порядка| OrderFixer[Исправление порядка<br/>см. диаграмму выше]
    
    OrderFixer -->|Правильный порядок| ImageElements[Element IMAGE<br/>с метаданными:<br/>- путь к изображению<br/>- подпись<br/>- координаты<br/>- номер страницы]
    
    TableExtractor -->|Структура таблицы| TableProcessor[Обработка таблиц]
    
    TableProcessor -->|Экспорт| TableFormat{Формат экспорта}
    
    TableFormat -->|HTML| HTMLTable[HTML таблица<br/>со структурой]
    TableFormat -->|Markdown| MarkdownTable[Markdown таблица<br/>с объединёнными ячейками]
    
    HTMLTable --> TableElements[Element TABLE<br/>с метаданными:<br/>- HTML/Markdown контент<br/>- подпись<br/>- структура ячеек]
    MarkdownTable --> TableElements
    
    FormulaExtractor -->|Формулы из DOCX| FormulaProcessor[Обработка формул]
    
    FormulaProcessor -->|Формат формулы| FormulaFormat{Формат формулы}
    
    FormulaFormat -->|OMML| OMMLFormula[OMML формат<br/>Office Math Markup Language]
    FormulaFormat -->|MathML| MathMLFormula[MathML формат<br/>Mathematical Markup Language]
    FormulaFormat -->|Изображение| ImageFormula[Распознавание по изображению<br/>OCR формулы]
    
    OMMLFormula --> FormulaElements[Element FORMULA<br/>с метаданными:<br/>- формула в формате<br/>- координаты<br/>- контекст]
    MathMLFormula --> FormulaElements
    ImageFormula --> FormulaElements
    
    ImageElements --> ElementCreator[Создание Element]
    TableElements --> ElementCreator
    FormulaElements --> ElementCreator
    
    ElementCreator -->|С правильной привязкой| FinalElements[Список Element<br/>со структурными элементами]
    
    style Docx fill:#e1f5ff
    style ImageProcessor fill:#fff4e1
    style TableProcessor fill:#e8f5e9
    style FormulaProcessor fill:#f3e5f5
    style FinalElements fill:#c8e6c9
```

## Разрешение ссылок на структурные элементы

```mermaid
graph TB
    Text[Текст документа] --> LinkDetector[Детектор ссылок]
    
    LinkDetector -->|Регулярные выражения| RegexMatcher[Regex поиск ссылок]
    
    RegexMatcher -->|Паттерны| Patterns[Паттерны ссылок:<br/>- см. рис. 1<br/>- см. табл. 2<br/>- рис. 1<br/>- таблица 3<br/>- график 1<br/>- диаграмма 2<br/>- схема 1<br/>- фотография 1]
    
    Patterns -->|Найдены ссылки| SimpleLinks[Простые ссылки<br/>регулярные выражения]
    
    Patterns -->|Сложные случаи| ComplexLinks[Сложные ссылки<br/>требуют LLM]
    
    SimpleLinks -->|ID элемента| LinkResolver[Разрешение ссылок]
    
    ComplexLinks -->|LLM анализ| LLMAnalyzer[LLM для определения ссылок]
    
    LLMAnalyzer -->|Контекстный анализ| LLMResult[Результат LLM:<br/>тип элемента + номер]
    
    LLMResult --> LinkResolver
    
    LinkResolver -->|Поиск элемента| ElementFinder[Поиск элемента<br/>по типу и номеру]
    
    ElementFinder -->|Найден элемент| ElementID[ID элемента<br/>или ID подписи]
    
    ElementID -->|Создание ссылки| LinkElement[Элемент со ссылкой<br/>в metadata:<br/>references: list of IDs]
    
    LinkElement -->|Обновление текста| UpdatedText[Текст с ссылками<br/>или metadata с references]
    
    UpdatedText --> FinalElements[Элементы со ссылками<br/>на структурные элементы]
    
    style Text fill:#e1f5ff
    style RegexMatcher fill:#fff4e1
    style LLMAnalyzer fill:#f3e5f5
    style LinkResolver fill:#e8f5e9
    style FinalElements fill:#c8e6c9
```

## Процесс LLM семантического детектирования заголовков с перекрытием

```mermaid
graph TB
    Text[Текст из DOCX] --> Chunker[Разбиение на чанки<br/>~3000 символов<br/>перекрытие: 1 параграф]
    
    Chunker -->|Чанк 1| Chunk1[Чанк 1<br/>без контекста]
    Chunker -->|Чанк 2| Chunk2[Чанк 2<br/>с перекрытием]
    Chunker -->|Чанк N| ChunkN[Чанк N<br/>с перекрытием]
    
    Chunk1 -->|Первый запрос| LLM1[LLM запрос 1:<br/>Определить заголовки по смыслу]
    
    LLM1 -->|Результат| Result1[Структура чанка 1:<br/>- Заголовки с уровнями<br/>- Классификация элементов<br/>- Иерархия]
    
    Result1 -->|Передать контекст| Chunk2Context[Чанк 2 +<br/>предыдущие заголовки]
    
    Chunk2Context -->|Следующий запрос| LLM2[LLM запрос 2:<br/>Определить заголовки по смыслу<br/>с учётом существующих]
    
    LLM2 -->|Проверка логики| LogicCheck[Проверка логики:<br/>внутри HEADER_2<br/>не может быть HEADER_1]
    
    LogicCheck -->|Корректная структура| Result2[Структура чанка 2:<br/>- Новые заголовки<br/>- Элементы<br/>- Иерархия]
    
    Result2 -->|Передать контекст| ChunkNContext[Чанк N +<br/>все предыдущие заголовки]
    
    ChunkNContext -->|Последний запрос| LLMN[LLM запрос N:<br/>Определить заголовки по смыслу<br/>с полным контекстом]
    
    LLMN -->|Финальная структура| ResultN[Структура чанка N]
    
    Result1 --> Merge[Объединение структур]
    Result2 --> Merge
    ResultN --> Merge
    
    Merge -->|Предварительная структура| PreStructure[Предварительная структура<br/>от LLM семантического анализа]
    
    PreStructure -->|Проверка и корректировка| Validation{Вариант проверки}
    
    Validation -->|Вариант 1| StyleValidation[Проверка через<br/>встроенные стили]
    
    Validation -->|Вариант 2| XMLValidation[Проверка через LLM<br/>с XML разметкой]
    
    StyleValidation -->|Скорректированная| FinalStructure[Финальная структура<br/>после проверки]
    
    XMLValidation -->|Скорректированная| FinalStructure
    
    FinalStructure -->|Применить к тексту| TextHierarchy[Иерархия текста<br/>с parent_id]
    
    style Text fill:#e1f5ff
    style Chunker fill:#fff4e1
    style LLM1 fill:#f3e5f5
    style LogicCheck fill:#e8f5e9
    style PreStructure fill:#e3f2fd
    style Validation fill:#fff9c4
    style FinalStructure fill:#c8e6c9
    style TextHierarchy fill:#c8e6c9
```

## Классовая структура DocxParser

```mermaid
classDiagram
    class BaseParser {
        <<abstract>>
        +DocumentFormat format
        +ElementIdGenerator id_generator
        +can_parse(Document) bool
        +parse(Document)* ParsedDocument
    }
    
    class DocxParser {
        +parse(Document) ParsedDocument
        -_parse_with_style_validation(Document) ParsedDocument
        -_parse_with_xml_validation(Document) ParsedDocument
        -_extract_structural_elements(str) dict
    }
    
    class DocxExtractor {
        +extract_text(str) str
        +extract_metadata(str) dict
        +extract_styles(str) dict
        +extract_xml_markup(str) str
        +get_paragraphs(str) List~Paragraph~
    }
    
    class LLMSemanticAnalyzer {
        +detect_headers_by_semantics(str, List~Header~) dict
        +classify_elements(str) List~Element~
        +build_hierarchy(str) dict
    }
    
    class StyleParser {
        +parse_styles(List~Paragraph~) List~Element~
        +map_style_to_element_type(str) ElementType
        +get_header_level(str) int
    }
    
    class StructureCorrector {
        +correct_with_styles(llm_structure, style_structure) dict
        +compare_structures(dict, dict) dict
        +apply_corrections(dict, dict) dict
    }
    
    class XMLParser {
        +parse_xml_markup(str) dict
        +extract_styles_from_xml(str) dict
        +extract_structure_from_xml(str) dict
    }
    
    class LLMValidator {
        +validate_structure_with_xml(llm_structure, xml_structure) dict
        +check_markup_consistency(dict, dict) dict
    }
    
    class ImageOrderFixer {
        +fix_image_order(List~Image~, List~Caption~) List~Image~
        +match_by_page_position(List~Image~) dict
        +match_by_context(List~Image~, str) dict
        +match_by_llm_comparison(List~Image~) dict
    }
    
    class TableExtractor {
        +extract_tables(str) List~Table~
        +export_to_html(Table) str
        +export_to_markdown(Table) str
    }
    
    class FormulaExtractor {
        +extract_formulas(str) List~Formula~
        +convert_omml_to_mathml(OMML) str
        +recognize_from_image(Image) str
    }
    
    class LinkResolver {
        +detect_links(str) List~Link~
        +resolve_references(str, List~Element~) List~Element~
        -_regex_match(str) List~Link~
        -_llm_match(str) List~Link~
    }
    
    class Element {
        +str id
        +ElementType type
        +str content
        +str parent_id
        +dict metadata
    }
    
    BaseParser <|-- DocxParser
    DocxParser --> DocxExtractor : использует для извлечения
    DocxParser --> StyleParser : использует для встроенных стилей
    DocxParser --> LLMSemanticAnalyzer : использует для семантики
    DocxParser --> ImageOrderFixer : использует для изображений
    DocxParser --> TableExtractor : использует для таблиц
    DocxParser --> FormulaExtractor : использует для формул
    DocxParser --> LinkResolver : использует для ссылок
    DocxParser --> Element : создаёт
```

## Сравнение вариантов проверки

```mermaid
graph TB
    Docx[DOCX файл] --> LLMSemantic[LLM семантический анализ<br/>с перекрытием]
    
    LLMSemantic -->|Предварительная структура| Comparison{Сравнение вариантов<br/>проверки разметки}
    
    Comparison -->|Вариант 1| StyleCheck[Проверка через встроенные стили]
    
    Comparison -->|Вариант 2| XMLCheck[Проверка через LLM<br/>с XML разметкой]
    
    StyleCheck --> StylePros[Плюсы проверки стилями:<br/>- Быстро<br/>- Точное сравнение<br/>- Не требует дополнительный LLM запрос<br/>- Дешевле]
    
    StyleCheck --> StyleCons[Минусы проверки стилями:<br/>- Требует наличие стилей<br/>- Простое сравнение<br/>- Может не учесть контекст]
    
    XMLCheck --> XMLPros[Плюсы проверки XML через LLM:<br/>- Умная проверка<br/>- Учитывает контекст<br/>- Может найти сложные несоответствия<br/>- Работает даже если стили неполные]
    
    XMLCheck --> XMLCons[Минусы проверки XML через LLM:<br/>- Требует дополнительный LLM запрос<br/>- Медленнее<br/>- Дороже<br/>- Зависит от качества LLM]
    
    StylePros --> Decision{Решение}
    StyleCons --> Decision
    XMLPros --> Decision
    XMLCons --> Decision
    
    Decision -->|Приоритет| Priority[Вариант 1 - по умолчанию<br/>Вариант 2 - для сложных случаев<br/>или когда нужна более точная проверка]
    
    Priority --> FinalChoice[Гибридный подход:<br/>LLM семантика + проверка<br/>стилями или XML через LLM]
    
    style Docx fill:#e1f5ff
    style LLMSemantic fill:#fff4e1
    style Comparison fill:#e8f5e9
    style Decision fill:#e8f5e9
    style FinalChoice fill:#c8e6c9
```
