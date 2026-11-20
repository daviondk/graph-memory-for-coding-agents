# Как повторить серию

Все пути в коде разрешаются относительно work/graph_memory_round4/writer. При переносе в другую папку потребуется такое же дерево зависимостей R3, R2 и memory_session5/packets. Веса и протоколы в некоторых SHA-манифестах указывают исходные абсолютные пути D. Единицей сравнения служит запись в файле *.jsonl.gz, наборы заморожены до расчёта показателей. Для переоценки скопируйте пакеты в новую рабочую копию. Программы предсказания сохраняют свои журналы под фиксированными именами, некоторые фазы останавливаются при существующем lock.

Для вычислений использовался CPU и Python 3.14 с NumPy. Этап выборки официального списка требует PyArrow в старом рабочем окружении с Python 3.12. Общий исходник R3 — work/graph_memory_round3/real_swe/acquire.py, базовый писатель — real_swe_followup/writer_followup.py, общий код воспроизведения ограничений и потоковых наблюдений находится в R2 span_memory, edit_memory и memory_session5/packets. В рабочей раскладке:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
py -V:Astral/CPython3.12.13 choose_roster.py
python acquire_data.py
python dictionary.py
python risk.py
python experiment.py predict B
python experiment.py grade B
python experiment.py predict A
python experiment.py grade A
python audit_controls.py
python freeze.py
python experiment.py predict C
python experiment.py grade C
python ablations.py
```

Для двусторонней привязки в каталоге anchor:

```powershell
python run_anchor.py predict
python run_anchor.py grade
python audit_target.py
python source_check.py
python holdout_anchor.py predict
python holdout_anchor.py grade
```

Для нового агента в каталоге source_kimi:

```powershell
python acquire_k.py
python test_k.py predict
python test_k.py grade
python audit_display.py
```

После этого в anchor запускаются python factorial.py predict и python factorial.py grade. Для оценки сохранённых предсказаний достаточно соответствующей фазы grade. Нужны принятые проекции source_k и снимки cuts/events, которые остаются на диске. Если эти большие файлы отсутствуют в поставке, их можно воспроизвести из приложенных проекций/официальных источников в новом каталоге. Публичные данные читаются по HTTPS, команды и код проектов из журналов ни разу не исполняются.

