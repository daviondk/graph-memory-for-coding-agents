# Сборка отчёта о графовой памяти

Исходники каждого раздела лежат в pages/ в порядке имени файла. Генератор использует python-docx и стили предыдущего отчёта, ссылку на который фиксирует artifact.md. В процессе не редактируется исходный Word предыдущего раунда.

Из PowerShell в этой папке использовать `C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` и по одному последовательно выполнить скрипты witness_figure.py, build.py, render.py, qa.py, source_audit.py, publish.py. Официальный bundled renderer вызывает переносимый soffice в D:/CodexResearch/x20-office-renderer/program и Poppler из Codex workspace dependencies. Повторное преобразование PDF может дать другую временную метку и другой хеш файла при том же тексте и геометрии. Ветка G2 отдельно проверена на Python 3.13 и 3.14.

В source_audit девять количественных таблиц сравниваются с исходными JSON, а текст всех тринадцати таблиц — с DOCX. QA проверяет каждую страницу PDF, число и заголовки страниц, координаты текста, ссылки и наличие визуализации. После финальной визуальной проверки PDF и Word скопированы в outputs/ без изменения источников экспериментов. sha256 итоговых артефактов фиксируется в final/released.json.
