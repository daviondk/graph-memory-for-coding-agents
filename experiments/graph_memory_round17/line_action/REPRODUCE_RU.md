# Воспроизведение инструментального выбора

Опыт использует входы R16/anchor_transfer и R17/line_selection, авторскую разметку SWE-Explore и официальный SWE-bench Verified parquet. Нужны Python, PyArrow, unidiff. Для повторного выполнения запроса необходимы локальные llama.cpp и Qwen3.8-27B UD-Q4_K_M; сведения об исходной конфигурации в launch.json. Полные базовые blobs лежат в D:/CodexResearch/x20-anchor-transfer/base. Блоки памяти содержат только подлинные показанные строки. У каждого есть имя файла, номера строк и содержимое, которое должно совпасть с базовым SHA репозитория.

Для разбора готового опыта используются сохранённые calls.jsonl, actions.json.gz, evaluation.json.gz и results.json. Независимая проверка исходных ответов и пересчёт precision и recall выполняются командой python verify.py. При наличии кеша R16 можно заново выполнить python read_spans.py и python evaluate.py. При перезапуске responses шаг study.py run находит завершённые вызовы по хешу. Для отдельной независимой репликации создайте свежую копию кода, протокола и launch-скрипта, не перезаписывая исходные ответы. Порядок стадий приведён ниже.

```powershell
python study.py prepare
.\start_server.ps1
python study.py run
.\stop_server.ps1
python read_spans.py
python evaluate.py
python diagnostics.py
python verify.py
```

Сценарий запуска занимает только свободный порт 18952, записывает PID и конфигурацию. Завершайте породивший эксперимент процесс по записи launch.json с проверкой идентичности исполняемого файла, PID и порта. Сквозные измерения стоимости собраны из поля usage каждого нативного ответа. Запуск на другой сборке, квантовании или GPU может дать другие ответы. [Назначение и хеши](design.lock.json) · [Исходные прогнозы](../line_selection/prediction-lock.json) · [Верифицированные наблюдения](../../graph_memory_round16/anchor_transfer/inputs.lock.json)
