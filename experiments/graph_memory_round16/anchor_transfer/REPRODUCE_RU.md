# Воспроизведение и хранилище исследования

Исходная среда Windows с Python, PyArrow и обычным доступом к HTTPS. В рабочей копии ожидаются D:/CodexResearch/x20-bench-workspace/work/graph_memory_round3/real_swe/official_verified.parquet, graph_memory_round11/readback/views.gz, graph_memory_round15/external_scoring/views.py с views-seal.json и native-source.json. В D:/CodexResearch/x20-round15-external-scoring находятся оригинальный pinned swe_eval.py и данные swe-explore.jsonl. URL меток и оценщика зафиксированы в R15/external_scoring/coverage.json и native-source.json. На другой машине пути WORK, CACHE и OFFICIAL определены в cohort.py. Все исходные команды из траекторий обрабатываются как текст. Никаких вызовов модели для воспроизведения не требуется.

Проверить сохранённые прогнозы и нативную оценку можно в каталоге опыта командой python score.py. Скрипт проверяет predictions.lock.json и SHA-256 внешнего кода и меток. Воспроизведение данных с первоначальным отбором в отдельной копии выполняется последовательно.

```powershell
python cohort.py
python observations.py
python policies.py
python score.py
python verify.py
```

При воспроизведении исторически замороженной когорты используйте поставленные cohort.json и cohort.lock.json и начинайте с observations.py. Поздние изменения публичного каталога могут изменить результат повторного cohort.py. У каждого выбранного объекта известны URI, S3 ETag и SHA-256 исходной траектории. Ресурсы кешируются на диске D:/CodexResearch/x20-anchor-transfer. Полные сырые ответы сохранены там отдельно. input-priors.json.gz содержит фактически передаваемые тексты, номера строк и идентификаторы событий. verify.py выполняет проверку хешей сырых файлов, всех стадий фиксации и независимо вычисляет пересечения строк. Если перенесены только компактные записи, воспроизведение observations.py загрузит исходные траектории. [Когорта](cohort.json) · [Разметка публичного выпуска](https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/tree/bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9)
