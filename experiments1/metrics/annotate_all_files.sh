#!/bin/bash
# Скрипт для разметки всех PDF файлов
# Использование: bash annotate_all_files.sh

echo "========================================"
echo "Разметка всех PDF файлов"
echo "========================================"
echo ""

# Файл 1
echo "[1/5] Разметка: 2412.19495v2.pdf"
python manual_annotation_tool.py --input test_files_for_metrics/2412.19495v2.pdf --output annotations/2412.19495v2_annotation.json
echo ""

# Файл 2
echo "[2/5] Разметка: 2506.10204v1.pdf"
python manual_annotation_tool.py --input test_files_for_metrics/2506.10204v1.pdf --output annotations/2506.10204v1_annotation.json
echo ""

# Файл 3
echo "[3/5] Разметка: 2508.19267v1.pdf"
python manual_annotation_tool.py --input test_files_for_metrics/2508.19267v1.pdf --output annotations/2508.19267v1_annotation.json
echo ""

# Файл 4
echo "[4/5] Разметка: journal-10-67-5-676-697.pdf"
python manual_annotation_tool.py --input test_files_for_metrics/journal-10-67-5-676-697.pdf --output annotations/journal-10-67-5-676-697_annotation.json
echo ""

# Файл 5
echo "[5/5] Разметка: journal-10-67-5-721-729.pdf"
python manual_annotation_tool.py --input test_files_for_metrics/journal-10-67-5-721-729.pdf --output annotations/journal-10-67-5-721-729_annotation.json
echo ""

echo "========================================"
echo "Разметка завершена!"
echo "========================================"
