# Повторение

Из папки retrieval на исходной машине команды ниже создают метод, прогнозы и поштучные пары. Для отдельной проверки исходной поставки сохранить её неизменную копию. Каждая следующая команда запускается после завершения предыдущей. CPU используется во всех частях.

```powershell
$researchPy = '../../graph_memory_round2/multihop/dev_env/Scripts/python.exe'
$encoderPy = '../../graph_memory_round4/encoder/.venv/Scripts/python.exe'
& $researchPy -B run.py
& $researchPy -B native_transfer.py
& $researchPy -B neural_transfer.py prepare
& $encoderPy -B neural_transfer.py infer
& $researchPy -B ablate.py
& $researchPy -B audit_inputs.py
& $researchPy -B author_crop.py prepare
& $encoderPy -B author_crop.py infer
& $researchPy -B grade.py
& $researchPy -B native_diagnostic.py
& $researchPy -B alignment_diagnostic.py
& $researchPy -B fetch_python_archive.py
& $researchPy -B replicate.py
& $researchPy -B archive_encoder.py prepare
& $encoderPy -B archive_encoder.py infer
& $researchPy -B archive_encoder.py grade
& $researchPy -B verify_independent.py
& $researchPy -B report_tables.py
```

run.py вычисляет пути к соседним сериям от собственного каталога. Метод использует замороженные модели, скрипты, двухъязычные входы и проверенные поштучные прогнозы R4 и R5. Python train для нового метода не используется. В method_lock.json зафиксированы SHA-256 исходных Parquet, препроцессора, ранжировщиков, кешей, индексов панелей и внешних предсказаний. Пути в roster.json относятся к этой машине; новый запуск run.py перестраивает их для текущего дерева. native_transfer.py использует исходный поставляемый Semlith 0.36.0 и модель, указанные в native_lock.json. При чистой репликации запускать на пустом каталоге native внутри рабочей копии R6 для холодного построения индекса. Внешние файлы предыдущих серий открываются только для чтения. Подробная подготовка исходных данных — в REPRODUCE.md соседних серий graph_memory_round4/repo, graph_memory_round4/encoder и graph_memory_round5/retrieval. Версии основных библиотек — в method_lock.json и encoder_receipt.json. Дополнительные зависимости Python для статистики не устанавливаются.

decisions.jsonl.gz содержит собственные и прежние полные списки в трёхстрочном режиме поставщика. ablation_decisions.jsonl.gz дополняет их списками двух диагностических моделей. В native_python_*.jsonl.gz столбцы panel, idx, project, число найденных файлов перед дополнением и окончательный порядок. new_encoder.jsonl.gz записывает Python cosine и порядок UniXcoder. В author/ используются отдельные предсказания точной архивной обрезки. При идентичном тексте запроса повторно взят ранее запечатанный порядок этого же энкодера. Для каждого наблюдения в paired.jsonl.gz указаны версия панели, ключ, проект, размер пула, эталон и позиция эталона у каждого ранжировщика. Целочисленные @1/3/5, MRR, два первичных p, коррекция Holm, интервалы по проектам и равновзвешенные средние сохранены в results.json. Невалидный индекс отражается null в рангах. Страты заполнены без фильтра по результату.

Для сверки повторного запуска сравнивать распакованный JSON, все перестановки и числа. Годы и временные метки входят в журналы, gzip включает время создания, pickle сохраняет внутреннее состояние реализации scikit-learn: побайтовый SHA удостоверяет именно отданную копию.

Источник дополнительной репликации — Python retrieval из архивного test.zip, ссылка издателя и CRC/SHA каждого члена в replication/prereg.json и replication/source.json. Загрузчик использует HTTP-диапазоны и библиотеку requests из уже имеющегося окружения энкодера. Изначальная попытка импорта requests только из исследовательского окружения завершилась до открытия архива. Для каждого примера члены Python-примитивов переведены в Parquet; стадия отборки и ранжирования имеет проекции колонок без эталона. Подпанель энкодера содержит 32 случая из каждой страты, максимум 2 одного проекта на страту. В replication/results.json раздел raw использует исходные имена всех методов. Раздел stats.full обозначает облегчённый метод в качестве исследуемого, stats.original_full обозначает полный R6. Во вложенном replication/encoder/results.json действует та же оговорка для раздела alignment.
