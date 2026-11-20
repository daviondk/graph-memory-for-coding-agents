# Сборка и проверка отчёта

Файлы страниц в `pages` содержат научный текст, таблицы и ссылки. `figure.py` строит интервальный график прямо из `../literature/results.json`. `build.py` собирает страницы в порядке имён. Сводки экспериментов находятся в каталогах `../reader`, `../validity`, `../literature`, `../repair` и `../concord`. Отдельные протоколы и исходные оценки сохраняют собственные знаменатели.

Среда выпуска — Windows, Codex primary runtime 26.1117.12345, Python 3.12.14, python-docx 1.2.0, Pillow 13.0.0, pypdf 6.21.4, pdfplumber 0.11.9 и ReportLab 4.4.9. Для растров использован Poppler из этого же комплекта. Файл `render_docx.py` взят из documents 26.1117.12345. На Windows комплект использует нативный конвертер с PATH. Указан отдельный экземпляр LibreOffice 26.8.3.1 в `D:/CodexResearch/x20-office-renderer/program`, подготовленный для исследовательских отчётов. Текст набирается Calibri и Cambria, на рисунке используется Arial.

Команды из каталога `report` в PowerShell:

```powershell
$reportPython = "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
& $reportPython figure.py
& $reportPython build.py
& $reportPython render.py
& $reportPython qa.py
```

Открыть все `final/page-*.png`, проверить расположение заголовка, таблиц, рисунка и разрывов страниц. После визуальной приёмки `& $reportPython publish.py` сохраняет обе версии в `../../../outputs` и сверяет контрольные суммы копий. `final/qa.json` содержит число слов, список гиперссылок, хеши изображений, границы текста и результаты независимой проверки чисел в таблицах через source_audit.py. `final/released.json` содержит SHA-256 конечных файлов. Время экспорта и метаданные PDF могут изменяться при новой сборке.
