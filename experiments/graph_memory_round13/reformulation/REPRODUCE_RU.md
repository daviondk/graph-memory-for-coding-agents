# Воспроизведение прогноза адресов

## Проверка скачанного каталога

Достаточно стандартной библиотеки Python. В опубликованном пакете присутствуют снимки до вызова, ранжирования, поштучные метки и хеши исходных историй. В каталоге с rank.py выполните:

```powershell
python -B verify_archive.py
```

Команда проверяет SHA всего манифеста, заново ранжирует все 340 состояний памяти и вычисляет Hit@1, Hit@3 и MRR всех шести политик для двух первичных исходов в двух панелях. Индивидуальные файлы в pr_refs содержат URL и SHA объединённого PR. В patch_labels.json.gz для каждой задачи сохранены официальный base, время, первый родитель и списки изменений. В navigation_labels.json.gz у каждого наблюдения есть идентификатор инструмента, команда, SHA видимого текста и положение относительно пустого поиска. Различия top-1 и поддерживающие общие идентификаторы находятся в discordances.json. Внешняя панель повторяет эту структуру внутри replication.

## Построение из первоисточников

Исходная среда серии — Windows, Python 3.14.4, Git. Корпус VibeMemBench с SHA из [публичного дерева](https://huggingface.co/datasets/Tongyi-ConvAI/VibeMemBench/tree/11164976b4f920cdb0d0cd570ca572e49acea1e8) использован только на чтение, под D:/CodexResearch/x20-official-vibe/VibeMemBench. Нужны benchmark/history/python и сохранённый список публичных blob SHA в memory-stage-fetch/source-manifest.json. Размеченные исходные Git-версии взяты из [SWE-rebench-V2](https://huggingface.co/datasets/nebius/SWE-rebench-V2/tree/d7608f017a29ab256400ad4b73d5248d97204966). Локальный кэш его Parquet находится в D:/CodexResearch/x20-round12-negative-objects/SWE-rebench-V2.parquet.

Для повторного отбора основной фиксированной панели требуются соседние work/graph_memory_round12/negative_external/extract.py, roster.json, task_meta_panel.json и pr_metadata.json. SHA парсера и roster лежат в input.lock.json. Для полного восстановления из оригиналов расположите их как в окружении серии или задайте пути для собственной копии скриптов. Независимая проверка из первой секции работает из этого каталога без предыдущих серий, интернета или Git.

Основной порядок команд сохраняет изоляцию прогнозов от оценки.

```powershell
python -B prefix.py
python -B rank.py
python -B navigation.py
python -B pr_oracle.py
python -B grade.py
```

Команды для панели новых репозиториев перечислены ниже. В команде meta допустим свой интерпретатор с pyarrow.

```powershell
python -B replicate.py freeze
python -B centrality.py
D:/CodexResearch/x20-official-vibe/solver-runtime/agent-venv/Scripts/python.exe -B replicate.py meta
python -B replicate.py nav
python -B replicate.py patch
python -B replicate.py score
python -B audit.py
python -B causal_prefix.py
python -B diagnostics.py
```

Метки патча после заморозки берутся из публичных GitHub PR и Git tree. Небольшие метаданные страницы PR кэшируются в pr_refs, а разреженные bare-зеркала хранятся отдельно в D:/CodexResearch/x20-round13-reformulation-objects. Эти зеркала, внешние исполняемые файлы и копии полных историй в манифест не включены. Для автономного пересчёта достаточно сохранённых наблюдений. При полном повторе рекомендована отдельная копия папки. Метки и порядок файлов детерминированы. Исходные записи времени отдельных прогнозов и сводки времени зависят от нагрузки на процессор, из-за чего при новой записи меняется SHA архива с таймингами. В опубликованном состоянии проверка verify_archive.py доступна без перезаписи.

[Основная фиксация](forecast.lock.json) · [Фиксация внешней панели](replication/forecast.lock.json) · [Поштучные метрики основной панели](per_anchor_scores.json.gz) · [Сводный отчёт](REPORT_RU.md)
