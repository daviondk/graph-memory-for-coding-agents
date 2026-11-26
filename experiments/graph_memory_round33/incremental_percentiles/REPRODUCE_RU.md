# Воспроизведение проверки

Запуск из graph_memory_round33/incremental_percentiles. Числовые фикстуры fixture-0…7.json.gz сохранены в модуле. Для проверки по ним требуются Python с NumPy и SciPy, соседние зафиксированные порядки R19/R33, относительные веса R33 и исходная ранговая модель R20. Для нативного замера g++ должен находиться в PATH. Проверенный компилятор и флаги зафиксированы в native-results.json.

```powershell
$researchPy = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $researchPy -B verify_manifest.py
& $researchPy -B runs.py verify
& $researchPy -B runs.py bench
& $researchPy -B native_run.py
& $researchPy -B recheck.py
```

Для повторной сборки фикстур из оригинальных данных первой командой запустить `& $researchPy -B fixtures.py`. Потребуются исходные траектории ISETrace, неизменённая нативная библиотека R18 и tokenizer.json, указанные в модуле R22/prefix_read. Отчёты фикстур и данные сохраняются на D. Нативная сборка и промежуточная числовая нагрузка располагаются в D:/CodexResearch/x20-r33-incremental-native. Тайминги живого CPU меняются между запусками. Проверять manifest исходного измерения следует до повторного запуска бенчмарка.