# Воспроизведение CPU-ранжировщика и абляций

Проверка сохранённого архива не требует графов или модели: `python -B verify.py` сверяет SHA-256, размеры бюджетов, групповые результаты и парные числа выигрышей и потерь. Для полного пересчёта нужны замороженные источники R17–R20 и предыдущие исходные корпуса; SHA входов, весов и прогнозов находятся в prediction-plan.json, fit-seal.json и forecast-seal.json. Структура относительных путей должна соответствовать дереву раундов. Переменные GRAPHMEMORY_REPO, ISETRACE_RESIDUAL, ISETRACE_TRAINED и TYPED_DATA задают локальный checkout автора, кэш графов, кэш обучающих PU и кэш дополнительных 21 графа. Среда использует Python 3.12, torch 2.6 CPU, scikit-learn 1.8.0, NumPy 2.5.5, pydantic, rank-bm25 и зависимости ISETrace. Классификаторы и вся графовая обработка работают на CPU с одним потоком BLAS.

Последовательность основного запуска:

```text
python -B study.py fit
python -B study.py predict 0 1 2 3 4 5 6 7
python -B study.py seal
python -B score.py
```

В ходе predict сравниваются все пары точных кандидатов с авторской функцией, числа степеней до/после перестановки и тождество исходному выбору prefix/skip из R19. Файлы forecast содержат индексы выбранных целых блоков в исходном списке rr. В первом шаге используются только метки dev. В score впервые читаются метки теста для измерения новых прогнозов. Для каждого из 2 000 запросов авторский span scorer сверяется с независимой реализацией объединения интервалов по event_id, JSON pointer и символьным координатам.

Дополнительный перенос рангов для обучения с BM25 на Dense и абляции:

```text
python -B train_bm25/transfer.py fit
python -B train_bm25/transfer.py infer
python -B score.py train_bm25
python -B mechanism/ablate.py fit dev
python -B mechanism/ablate.py infer dev
python -B score.py mechanism/test-dev
python -B mechanism/contrast.py dev
python -B mechanism/ablate.py fit train
python -B mechanism/ablate.py infer train
python -B score.py mechanism/test-train
python -B mechanism/contrast.py train
```

Дополнительная проверка 80 вопросов:

```text
python -B holdout80/graphs.py
python -B holdout80/heldout.py infer <frozen-rank-path> <SHA256>
python -B holdout80/heldout.py score <frozen-rank-path> <SHA256>
python -B strata.py
```

Для этих 80 вопросы хранятся в R19/write_transfer/cohort.json. Предыдущие реплики не запускаются. Графы для 53 общих траекторий загружаются из замороженного нативного кэша R20/residual_graph, ещё для 21 траектории нативный адаптер и тот же токенизатор повторно строят граф из закреплённых шардов ISETrace. Ключи индекса source-plan.json дают контрольные суммы каждого графа. Определение границ и стоимости кандидата сверяется с предыдущей проекцией. Нормализация или выбор весов по новой панели отсутствуют.

Исходная публикация, release кода, query-корпус и архив траекторий доступны по зафиксированным ссылкам. [Статья и нативные метрики](https://arxiv.org/html/2609.25913v3) · [Публичная реализация](https://github.com/xiaoqi-7/GraphMemory/tree/df29287116fa1565b3fd6b485022cd6090dc0b27) · [Запросы](https://huggingface.co/datasets/HazeLocus/ISETrace-Memory-Queries/tree/3130aeeaeb2b8d292c29f4c8e23303be7463732c) · [Траектории](https://huggingface.co/datasets/valiere/ISETrace/tree/e40e04d41c04e4eb4bae181ebdd41b61c688081b)
