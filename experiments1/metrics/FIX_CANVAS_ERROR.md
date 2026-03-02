# Исправление ошибки canvas

## Проблема

```
AttributeError: module 'streamlit.elements.image' has no attribute 'image_to_url'
```

Эта ошибка возникает из-за несовместимости версий `streamlit-drawable-canvas` и Streamlit.

## Решение

### Вариант 1: Обновить библиотеки

```bash
pip install --upgrade streamlit streamlit-drawable-canvas
```

### Вариант 2: Использовать совместимые версии

```bash
pip install streamlit==1.28.0 streamlit-drawable-canvas==0.9.0
```

### Вариант 3: Использовать альтернативный подход

Если проблема сохраняется, можно использовать ручной ввод координат вместо рисования.

## Проверка версий

```bash
pip show streamlit streamlit-drawable-canvas
```

## Альтернативное решение

Если `streamlit-drawable-canvas` не работает, можно:
1. Использовать режим "Просмотр" для просмотра PDF
2. Вводить координаты вручную в форму
3. Или использовать внешний инструмент для определения координат
