# Как собрать и проверить отчёт

Исходники страниц лежат в pages. А4 и стили Word берутся из открываемой копии отчёта предыдущего раунда `outputs/graph-memory-research-round2.docx`, SHA-256 c8752734c80847bfb36d10aa0d02628a6a5d1dc18199f8979b925583c07adc8e. Рисунок строит `serialized_writer/figure.py` по `curve_results.json`. В отчёте для него используется PNG, исходный PDF того же рисунка сохранён рядом.

В каталоге report в Windows выполнить следующие команды. Скрипт render.py находит установку LibreOffice на диске D и Poppler в комплекте Codex. Переопределять абсолютные пути нужно только при переносе на другой компьютер.

```powershell
$docPy = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $docPy class_page.py
& $docPy build.py
& $docPy render.py
& $docPy qa.py
& $docPy numeric_audit.py
& $docPy source_links.py
& $docPy publish.py
```

Данные для расчёта расположены в каталогах ветвей из общего архива раунда. Numeric audit сравнивает цифры исходных таблиц с машинными JSON, записывает их SHA-256 в final/numeric_audit.json. Записи final/source_links.json содержат разрешённые адреса и статус источников. Проверка qa.py ищет точное соответствие заголовков отдельных страниц, границы текста, графические файлы и все ссылки в DOCX. Растровая проверка выполняется по PNG каждой страницы после рендера конечного DOCX. В final/published.json записываются SHA-256 готовых версий. Для повторного проведения опытов использовать журналы и команды конкретной ветви в архиве.
