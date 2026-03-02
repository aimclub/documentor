@echo off
REM Команда для запуска комбинированного пайплайна DOCX на одном файле
REM Использование: run_docx_hybrid_pipeline.bat "путь_к_файлу.docx"

python experiments\pdf_text_extraction\docx_hybrid_pipeline.py "E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder\Диплом.docx"

pause
