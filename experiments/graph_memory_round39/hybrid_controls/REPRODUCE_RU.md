# Воспроизведение

Переносимая проверка всех поставленных артефактов и поштучных оценок использует стандартный Python. Каталог budget_curve должен находиться рядом с текущим каталогом. Начните с `python -B verify.py`.

Для полного повтора используются одни и те же локальные ранжирования двух R-GCN на пяти seed, подготовленные числовые признаки R33 и обе обученные ранее функции global_packet. Нужны окружение проекта с NumPy и штатным SDK ISETrace, GNU C++ и две библиотеки точного решения. В PowerShell выполните из этой папки в копии рабочего дерева:

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:R39_EXACT_FILL_DLL = Join-Path $env:TEMP 'r39-hybrid-exact.dll'
$env:R39_KNAPSACK_DLL = Join-Path $env:TEMP 'r39-residual-choice.dll'
g++ -O3 -std=c++17 -shared -static exact_fill.cpp -o $env:R39_EXACT_FILL_DLL
g++ -O3 -std=c++17 -shared -static ../remaining_budget/choose.cpp -o $env:R39_KNAPSACK_DLL
& $runner -B forecast.py 13 17 29 37 41
& $runner -B judge.py
& $runner -B analyze.py
& $runner -B check_solvers.py
& $runner -B check_intervals.py
```

Прогноз и оценщик сохраняют завершённые стадии. Для построения с иным компилятором, библиотеками или версией сжатия используйте отдельную копию с пустыми выходными файлами. В manifest.json указаны SHA-256 поставки, в run-log.jsonl — время и записи перезапуска. Файлы test-SEED-packets сохраняют по каждому вопросу траекторию и адреса в порядке «две модели, шесть бюджетов, восемь правил», перечисленном в test-SEED-seal. В test-SEED-outcomes находятся две площади, а затем для шести бюджетов Full Support, Coverage, токены и число узлов. Таблица curve-points.csv содержит 96 агрегированных комбинаций. В results.json записаны все средние, поштучно проверенные разности стоимости и интервалы при обеих схемах перевыборки.
