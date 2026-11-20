# Проверка и независимый прогон

Архив раскрывается в два соседних каталога, published и version. Второй содержит небольшие оригинальные контрольные записи внешнего потока. Все команды этой страницы выполняются из published. В исследовании использованы Windows CPython 3.14 для проекции R5 и анализа и Linux CPython 3.12.16, SQLite FTS5, PyYAML 6.0.3 для MemTrace. Для пересчёта статистики и проверки нужен NumPy. Сами оригинальные нативные библиотеки MemTrace включены из официального коммита с LICENSE и NOTICE.

Без изменения опубликованных файлов проверяются 14 фиксаций протокола, методов, входов и ответов, а также полная поэлементная идентичность трёх вариантов на Claude. Для официального теста ядра устанавливается также pytest 9.0.2.

```sh
python -m pip install numpy PyYAML==6.0.3 pytest==9.0.2
python -B verify_replay.py
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=MemTrace/src python -m pytest -p no:cacheprovider MemTrace/tests/unit/test_core_recall.py
```

Для повторного физического прогона всех пяти конфигураций нужны Linux, Python с SQLite FTS5 и место для отдельных копий каждой SQLite-базы. Названия воспроизведённых каталогов должны быть свободны. Сохранённые оригинальные результаты считаются неизменными. Каждый вызов последующей read-only проверки сравнивает с оригиналом из архива все отданные значения по каждому запросу. Для многократного чтения она также сравнивает реальные расходы на байты, число вызовов и число страниц. При Linux Python 3.14 и новее для многопроцессного запуска данных сценариев требуется контекст fork (рабочий интерпретатор Python 3.12.16 использует его по умолчанию).

```sh
python -B native.py replay_kimi --workers 4
python -B verify_replay.py --mode kimi --actual replay_kimi
python -B multiple.py replay_multiple --workers 4
python -B verify_replay.py --mode kimi_multi --actual replay_multiple
python -B hybrid.py replay_hybrid --workers 4
python -B verify_replay.py --mode kimi_hybrid --actual replay_hybrid
python -B external_run.py replay_claude
python -B verify_replay.py --mode claude --actual external/replay_claude
python -B symmetry_run.py replay_aligned
python -B verify_replay.py --mode aligned --actual external/replay_aligned
```

Для пересчёта табличных результатов можно последовательно выполнить только external_score.py и symmetry_score.py в рабочей копии с оригинальными запечатанными кадрами. Они восстанавливают all_results.json и symmetric_results.json. Начальные исследования сохранены в score.py, multi_score.py и hybrid_score.py со своими журналами. При отдельном повторе раннего оценщика используйте отдельную копию входного архива, так как gzip записывает свежую временную отметку даже при идентичном содержимом.

Проекции stream.jsonl.gz содержат уже извлечённый по порядку текст наблюдений, queries.jsonl.gz — внешний запрос, graph.jsonl.gz — исходную выдачу запечатанного кэша, answers.jsonl.gz — отдельный эталон. Каталог external использует те же имена. Для обеих панелей сохранены фактические публичные ответы MemTrace и сводки затрат каждого задания. Файлы all_paired.jsonl.gz и symmetric_paired.jsonl.gz связывают каждый исход с задачей. Чтобы заново извлечь исторические наблюдения из нативных файлов SWE-agent, prepare.py и external_prepare.py дополнительно требуют дерево предшествующих серий R2–R5 и version со state_lock.json и states_external_0.gz. В архиве приложены ссылки и контрольные суммы первичных исторических траекторий.
