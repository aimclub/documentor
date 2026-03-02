# Быстрый старт: Оценка метрик через Dedoc

## Шаг 1: Запустить Docker контейнер

```bash
# Запустить контейнер dedoc
docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc

# Проверить, что контейнер работает
docker ps | grep dedoc
# или
docker logs dedoc
```

## Шаг 2: Установить зависимости (если нужно)

```bash
# Если используете venv_dedoc
cd experiments/metrics
venv_dedoc\Scripts\activate  # Windows
# или
source venv_dedoc/bin/activate  # Linux/Mac

# Установить requests (для работы с Docker API)
pip install requests
```

## Шаг 3: Запустить оценку

```bash
python evaluate_dedoc.py
```

Скрипт автоматически:
- Обнаружит Docker API на порту 1231
- Обработает все PDF файлы из `test_files_for_metrics/`
- Вычислит метрики по ground truth аннотациям из `annotations/`
- Сохранит результаты в `dedoc_metrics.json`

## Остановка контейнера

```bash
docker stop dedoc
docker rm dedoc
```

## Примечания

- Скрипт автоматически определяет, использовать Docker API или локальную установку
- Если Docker API недоступен, скрипт попытается использовать локальную установку dedoc
- Для работы через Docker достаточно установить только `requests`
