# Воспроизведение

Запускать из этой папки. На исходной машине все входные данные, модели и журналы лежат на D:. Папки сравниваемых серий имеют общий родитель work, включая graph_memory_round2, graph_memory_round3, graph_memory_round4 и graph_memory_round5. Программы рассчитывают пути относительно собственного файла. Для чистого повторения сохраните исходную копию данной папки с неизменными результатами и запускайте вторую копию в соседней папке внутри graph_memory_round5. Создаваемые в рабочей копии файлы с теми же именами обновляются. Имена SHA-256 gzip-файлов зависят от времени создания gzip-заголовка; побайтовые хеши удостоверяют сохранённый оригинал. Для нового запуска сравнивайте распакованные JSON-строки, ранги, параметры и метрики с допуском на округление.

Использованы два существующих окружения Windows. Полный список зависимостей и версия Python записаны в environment.txt. Однопоточные операции NumPy с большими матрицами и FP32 PyTorch для UniXcoder исполняются на CPU. Финальная строка каждого блока должна успешно завершиться перед переходом к зависимому этапу.

```powershell
$researchPython = '../../graph_memory_round2/multihop/dev_env/Scripts/python.exe'
$encoderPython = '../../graph_memory_round4/encoder/.venv/Scripts/python.exe'

& $researchPython prepare_new.py
& $researchPython graph_data.py
& $researchPython neural_devlock.py
& $researchPython rank_model.py
& $encoderPython embed.py
& $researchPython neural_rank.py
& $researchPython score5.py rank
& $researchPython score5.py neural
& $researchPython budget.py
& $researchPython score_budget.py
& $researchPython budget_diagnostics.py
& $researchPython transfer.py
& $researchPython score_transfer.py
& $researchPython online.py
& $researchPython score_online.py
& $researchPython reserve.py
& $researchPython score_reserve.py
& $researchPython audit_reserve.py
& $researchPython audit.py
```

Необходимые внешние артефакты:

- В graph_memory_round4/repo имеются замороженные модели models.pkl, memory.py, full.pred.jsonl.gz, full.scores.jsonl.gz, archive.pred.jsonl.gz, python.pred.jsonl.gz и strict_java.pred.jsonl.gz, а также archive_results.json для независимого сопоставления трёх исходных списков. В inputs Java HF c9daeba525cb28cfb9fbe17886f32b8ea34fc870, архивные Java-примеры в archive_inputs. Входные данные Python находятся в graph_memory_round3/repo/inputs. Файлы R4 получают через программы и инструкции той серии. В частности, sources.json содержит ссылки на каждую исходную часть и контрольные суммы. [RepoBench-R HF](https://huggingface.co/datasets/tianyang/repobench-r/tree/c9daeba525cb28cfb9fbe17886f32b8ea34fc870) · [Авторский исходный архив](https://github.com/Leolty/repobench/tree/ccacd12a68783ca27e9997c3b754d3e9e0d958da).
- В graph_memory_round4/encoder имеются разметка development, слепые пакеты и запечатанные предсказания HF, скрипт repo_unixcoder.py и weights от microsoft/unixcoder-base. SHA-256 весов 6732b60037b086557e4c731c3748c99b4fec735d9ffe3c4c70061fd142e6b9d9. [Модель UniXcoder](https://huggingface.co/microsoft/unixcoder-base).

**Где смотреть.** В RESULT.md содержится интерпретация. В PROTOCOL_RU.md две первичные проверки, последующие решения задокументированы в файлах BUDGET_PROTOCOL_RU.md, TRANSFER_PROTOCOL_RU.md, TRANSFER_AMENDMENT_RU.md, ONLINE_PROTOCOL_RU.md и RESERVE_PROTOCOL_RU.md. Для воспроизводимости эмбеддингов сохранены data_lock.json, encoder_receipt.json, слепой корпус и индивидуальные cosine scores. Файлы rank_items.jsonl.gz и neural_items.jsonl.gz содержат позицию эталона в выдаче каждого метода, а соответствующие *predictions* — полные перестановки кандидатов. Порядок метрик в результатах @1, @3, @5, MRR, для каждой одновременно опубликованы pooled micro и project macro. Confidence interval разности двух моделей по независимой повторной выборке проектов (seed 20261118, 10 000 повторов); первичные p-value дополнительным двусторонним знаковым перестановочным тестом на суммах внутри проектов, 50 000 знаковых перестановок.

Файлы budget_items.jsonl.gz и transfer_items.jsonl.gz связывают глубины, результаты и конкретные ID запросов. Для последовательных методов файлы online_{java,python}.jsonl.gz и reserve_{java,python}.jsonl.gz содержат строки [panel, idx, repo, seed, t, depth_count_model, depth_harmonic, depth_uniform]; t — последовательный номер внутри данной перестановки начиная с нуля. Общая меточная таблица уже сохранена в transfer_items.jsonl.gz: выбирайте один режим, например mixed, и соединяйте по (panel,idx). Файлы online_result.json и reserve_result.json содержат реальный средний расход и все десять значений покрытия. Если требуется проверить баланс каждого проекта после каждого прочтения, запустите audit.py и audit_reserve.py. Имя поля old_graph_macro_match в audit.json историческое: проверка фактически сравнивает четыре **micro**-метрики базового графа, owner и Jaccard с R4.

