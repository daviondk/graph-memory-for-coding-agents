# Воспроизведение

Для перепроверки результата из архива достаточно Python 3.11+ и соседнего каталога `isetrace_official` с эталонными координатами. Из каталога `isetrace_e5` выполнить `python verify.py`. Проверка сверяет хеши, исполнение лимита и поштучно пересчитывает FS, символьное покрытие, плотность и F1 на 10 000 упакованных выборках исходных блоков. После вычисления per-query обе доверительные границы считаются отдельно по траекториям.

**Полный пересчёт E5.** Соседние каталоги R17 и R18 сохраняют структуру под `work/`. Внешние данные, веса и авторский checkout восстанавливаются по `graph_memory_round17/isetrace/provision.py`, `dense/provision_e5.py` и `isetrace_official/REPRODUCE_RU.md`. Снимки модели и датасета закреплены в inventory.json и исходном SHA-реестре. В исходном запуске Python 3.12.13, PyTorch 2.6.0+cu124, sentence-transformers 2.7.0, transformers 4.52.4, NVIDIA RTX 3090. Дополнительные версии и команды можно восстановить из скриптов предшествующих серий. Для нашего GPU была создана самостоятельная виртуальная среда на D с официальным wheel torch 2.6.0+cu124. Оставшиеся Python-библиотеки добавлены из существующих CPU-сред через два пути в .pth; предыдущие среды использовались только для чтения. `HF_HUB_OFFLINE=1` фиксирует работу из локально проверенных весов, `OPENBLAS_NUM_THREADS=1` ограничивает CPU-ранжировщик. Полная длина входа до 512 токенов с префиксами, batch_size=64.

В новой рабочей копии и с отдельным `ISE_E5_CACHE` выполнить команды. По умолчанию кеш на D. В подкаталоге projection хранится сырой текст, SQLite содержит точные ключи и сохранённые векторы, оба остаются вне архива.

```powershell
foreach ($i in 0..7) { python project.py $i }
python inventory.py
python encode.py bench
python forecasts.py plan
python placebo_e5.py plan
python budget_grid.py plan
python encode.py run
python cost.py
python vector_receipt.py
python forecasts.py run
python placebo_e5.py predict
python budget_grid.py predict
python cpu_check.py
python evaluate.py
python placebo_e5.py score
python budget_grid.py score
python sensitivity.py
python calibration.py
python report.py
```

В режиме полной FP32 схемы все запросы проходят один и тот же путь. Если повторный замер на другом устройстве автоматически выбирает mixed, дополнительно вычисляется калибровочная FP32 панель. В этом случае отчёт о точном воспроизведении полного FP32 следует составлять отдельно. На другом компьютере повторный байтовый SHA файла с длительностью запуска меняется закономерно. На инвариантных данных сопоставляются ID, калибровочные показатели, отобранные блоки и интервалы; округление при умножении матриц изучено отдельно в cpu-check.json.

Для негативного контроля нужны код и placebo-event-metadata соседнего официального исследования R18. Исходная таблица 1 содержит отдельные классы обучения. [Статья Wang et al.](https://arxiv.org/html/2609.25913v3) [Код авторов](https://github.com/xiaoqi-7/GraphMemory/tree/df29287116fa1565b3fd6b485022cd6090dc0b27) [Замороженные веса](https://huggingface.co/intfloat/e5-base-v2/tree/f52bf8ec8c7124536f0efb74aca902b2995e5bcd)
