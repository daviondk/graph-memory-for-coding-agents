# Сборка отчёта второго раунда

Исходный текст страниц и таблиц находится в `pages/`. Сборка Word использует формат предыдущего отчёта. Целевые файлы `graph-memory-research-round2.docx` и `graph-memory-research-round2.pdf` готовятся в `final/`, затем копируются в `outputs/`. Внутренние изображения для проверки доступны рядом с ними. Предыдущие отчёты не перезаписываются.

Использовать Python из Codex workspace dependencies, `C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`. В каталоге этого файла выполнить последовательно build.py, render.py, qa.py, numeric_audit.py. Windows-обёртка render.py вызывает поставляемый Documents render_docx.py через проверенный переносимый офис этого проекта и Poppler из workspace dependencies. `qa.py` проверяет заголовки, контуры текстовых блоков, структуру Word, ссылки и изображения всех страниц. `numeric_audit.py` сравнивает количественные ячейки Word с исходными JSON. Отчёты о проверке сохраняются в final/.
