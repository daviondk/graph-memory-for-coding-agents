# Воспроизведение

Запускать из этого каталога с доступными историческими кэшами на диске D. Команда prepare_scale.py собирает нативные плотные ранги из локальных эмбеддингов на CPU и создаёт numeric-train.npz. Матрица уже включена в исследование; из неё можно сразу повторить обучение командой run_remaining.py. При повторном запуске run-log.json будет содержать новые измерения времени.

```powershell
$experimentPython='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $experimentPython -X utf8 prepare_scale.py
& $experimentPython -X utf8 run_remaining.py
& $experimentPython -X utf8 audit.py
```

Структурные признаки происходят из подписанных шардов R20 и ролевых преобразований R33, исходный числовой кэш — из ранее воспроизведённого Dense-FT. Порядок строк numeric-train соответствует order в train-inventory, число кандидатов для вопроса задаёт records[q].n. Массив g содержит 23 графовых признака, z — 4 признака коррекции, c — стоимости и y — индикаторы пересечения с эталоном. Воспроизведение исходного R33 также включено в таблицы. Финальные исходы даны по каждому вопросу, ранги указаны нулевыми индексами в исходном Dense-порядке.

```powershell
$files = (Get-Content manifest.json -Raw | ConvertFrom-Json).files
foreach ($entry in $files.psobject.Properties) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Name).Hash.ToLowerInvariant() -ne $entry.Value) {throw $entry.Name}
}
```