# Проверка пятнадцатой серии

`package_local.py` проверяет SHA-256 каждого архивного файла и точный состав пяти отдельных исследований. Проверка готового ZIP требует стандартную библиотеку Python 3.11 или новее. Полное имя файла передайте как аргумент.

```powershell
python -B package_local.py D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round15-records.zip --verify
```

Исходные команды и зависимости приведены в документах отдельных исследований. Для проверки архива исходные объекты Git, веса модели, образы Docker и внешние метки не требуются. Для переисполнения агентных задач нужны зафиксированные версии решателя, образов и исходного бенчмарка. [Пути из вывода инструментов](frontier/REPORT_RU.md) · [Фактические чтения](menu_action/REPRODUCE_RU.md) · [Результаты pytest](test_receipts/REPORT_RU.md) · [Рабочее дерево](terminal/grading/REPRODUCE_RU.md) · [Оценщики локализации](external_scoring/REPRODUCE_RU.md)
