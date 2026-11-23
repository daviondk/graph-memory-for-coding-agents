# Как повторить обучение и оценку

Официальный проект GraphMemory, разрешённая ревизия сырья, 8 шардов v7 и входной tokenizer уже проверены в сериях R17–R18. Идентификаторы коммита, хеши авторских файлов и исходных весов приведены в source-audit.json. Рабочая копия предполагает каталоги `work/graph_memory_round17`, `work/graph_memory_round18` и `work/graph_memory_round19` с прежней иерархией. Для быстрой офлайн-проверки нужны данные из соседней R18. Интерпретатор Python 3.12.13, версии ML-библиотек в source-audit.json. Работа на D разделена между воспроизводимыми исходниками, запечатанными результатами и большим каталогом кэша `D:/CodexResearch/x20-isetrace-trained`.

**Источник выборки.** Документированный профиль авторов full выбирает все доступные train/test и 500 dev. Сначала используются фиксированные split_counts 2 410/352/1 207 и seed 13 из опубликованного адаптера ISETrace. Итоговые 3 894 train + 500 dev + 2 000 test сравниваются по идентификаторам, включая поштучный порядок test из предшествующего опыта. Сырые запросы всех разделов распространяются в одном JSONL. При создании обучающих примеров код берёт только train и dev из явно заданного реестра, для них вызывает авторское сопоставление наблюдений и преобразует символы в положительные блоки. Списки узлов test и их эталонные координаты к обучению не передаются.

**Чекпойнт.** Используется исходная модель E5-base-v2 f52bf8ec, один training seed. Конфигурация Dense-Finetune из full profile, одна эпоха, batch 16, FP32 без TF32, LR 0,00002, максимум градиента 1. Авторская поправка effective_for_dataset для ISETrace устанавливает число hard graph neighbors в ноль. На положительный элемент допустимы два лёгких негативных и два BM25; DenseFT-конвертер берёт один negative для обучающей тройки. Нативный trajectory sampler разрешает не больше одной тройки данной траектории в одном batch. Тренер вычисляет dev-показатели для epoch 0 и 1 и сохраняет лучший по dev_recall_at_5. Этот критерий относится к размеченным блокам. Recall@5 в основной таблице теста измеряется в координатах символов. Состояние после пробных шести шагов удаляется при выходе отдельного процесса замера; полный fit загружает исходные веса заново. [Статья](https://arxiv.org/html/2609.25913v3#S4.SS3) · [Авторские конфигурации](https://github.com/xiaoqi-7/GraphMemory/tree/df29287116fa1565b3fd6b485022cd6090dc0b27/configs)

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONUTF8='1'
python prepare.py assign
foreach ($i in 0..7) { python prepare.py $i }
python audit_sources.py
python train.py pairs
python train.py bench
python train.py run
python weight_audit.py
python test_retrieval.py lock
python direct_audit.py plan
python direct_audit.py rank
python test_retrieval.py embed
python test_retrieval.py predict
python score.py
python rank_diagnostics.py
python direct_audit.py check
python published_bounds.py
python rank_only_cost.py
python rgcn_cost.py
python artifact_audit.py
python report.py
```

Для преобразования входа модели используются авторские query/passage prefixes, 504 содержательных токена и overlap 64. External SQLite из R18 используется в режиме чтения только для исходных строк test. Все эти строки новый checkpoint кодирует заново, затем нативный DenseTaskRetriever вычисляет скалярные произведения. Новая база векторов привязана к SHA обученных весов. Снимки весов и полное содержимое запросов остаются в отдельном кэше. Архив содержит поштучные параметры, ранги, source spans и стоимость — их хватает для независимой оценки результата.

Быстрая проверка без GPU — `python verify.py`. Для неё нужен файл `isetrace_official/gold-spans.json.gz` из R18. Если R18 находится в другом месте, установить `ISE_R18` в абсолютный путь к её корню. Сама проверка использует стандартную библиотеку и перепроверяет интервалы, все пять упаковок, 6 метрик таблицы и непересечение разделов. Для будущего сопоставления со всей серией авторов требуются остальные training seeds 17, 29, 37, 41 и одинаковая политика чтения у сравниваемого R-GCN.

Первое подключение read-only test-кеша через SQLite ATTACH было прервано до записи любого вектора. Подробности и первоначальный SHA плана лежат в recovery/. Повтор принимает те же входы и веса, включает SQLite-параметр uri=True и фиксирует новый SHA кода до обработки.

В частности, _read_queries физически десериализует общий JSONL вместе с test gold, затем список активных примеров фильтруется по train/dev ID. Код не обеспечивает изоляцию read permissions между разделами. Проверка разделов касается данных, использованных в оптимизации и выборе checkpoint.
