# Воспроизведение восьмого раунда

В ZIP входят протоколы, код, зафиксированные входы экспериментов, выдачи и ранжирования по примерам, запросы и ответы локальной модели, результаты тестов, исследовательские журналы и отчёты четырёх серий. Точный перечень хранится в `MANIFEST.sha256`. Файлы в архиве размещены относительно корня раунда. Для сценариев, читающих историю прошлых раундов по относительным путям, рабочая структура имеет вид `work/graph_memory_round8`, по соседству с `graph_memory_round5`, `graph_memory_round6` и `graph_memory_round7`.

## Проверить и экспортировать

Упаковщику нужен Python 3.11 или новее со стандартной библиотекой. В каталоге R8 печать перечня, сборка в штатную папку outputs на диске D и проверка существующего файла выполняются следующими командами PowerShell.

```powershell
python package_local.py --list
python package_local.py
python package_local.py --verify D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round8-records.zip
```

Для записи всех отобранных и проверенных материалов в новую локальную папку добавьте `--export` к сборке или проверке. Укажите ещё не существующую папку. Это обычный экспорт файлов. Команды Git отсутствуют.

```powershell
python package_local.py --verify D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round8-records.zip --export D:/CodexResearch/graph-memory-round8-export
```

Альтернативный путь архива задаётся через `--output`. Для явного обновления существующего архива предназначен `--replace`. Сборку следует запускать после завершения экспериментов. Упаковщик проверяет неизменность входного перечня и его хешей за время записи. Времена членов ZIP, порядок, права доступа и способ хранения зафиксированы. Два запуска на одинаковых байтах источников дают одинаковый SHA-256 ZIP. По внутреннему манифесту проверяются целостность и состав. Для независимого контроля сохраните итоговый хеш ZIP отдельно.

## Проверить выводы по сохранённым записям

| Серия | Что можно проверить по архиву | Что требуется для повторного получения наблюдений |
|---|---|---|
| anchors | Таблицы рангов/меток, поэлементные исходы и числители. `python score.py` повторно склеивает запечатанные прогнозы с метками и записывает агрегаты. | Полная история Git трёх проектов в D:/CodexResearch/x20-round8-oracle-cache и внешний JSON oracle на указанной ниже ревизии. Для Git-контроля нужно запустить identity перед anchors/audit/git_range.py. |
| lazy | `python replay.py` и затем `python score.py`, `python ablation.py` работают на включённой проекции observations.gz. Код проверяет хеши собственных входов. | `python extract.py` и полная проверка `python verify.py` используют 29 исходных файлов R5–R7. В lazy/inputs.json указаны все относительные пути и SHA-256. |
| retrieval | Списки кандидатов/первые 40 результатов на задачу, разметка, оценки по задачам и срезам. `python verify.py` проверяет порядок, показатели и хеши. Нужен пакет requests для импорта acquire.py. | Для новой выдачи требуются официальный архив корпусов и запросов SweRank, соответствующая модель извлечения и её зафиксированный энкодер. Для запросов, на которых считается overlap с прошлым R7, проверка дополнительно читает graph_memory_round7/localization/scores_per_issue.json при его наличии. |
| agent, agent/compression, agent/handles | Локальные вызовы модели содержат исходные сообщения и ответы. Файлы задач, контроли, JSON результатов и XML/лог тестов дают возможность проверить конкретный патч и число прошедших тестов. `predictions_*.jsonl` содержат экспорт предсказаний там, где тестовая серия завершила экспорт. | Новая генерация требует прежней среды R6/R7, локального сервера с весами, токенизатора, доступных на D checkout-архивов SymPy и rg; точные зависимости берутся из agent/input_lock.json и input_lock.json дочерних серий. Повторный запуск тестов требует также рабочего окружения тестов SymPy и прежнего grade.py. |

Повторная оценка в экспериментальных скриптах записывает некоторые итоги по тем же именам. Для проверки поставленного архива без записи используйте `package_local.py --verify`. Для пересчёта распакуйте отдельную рабочую копию.

## Источники и зависимости

- **Рефакторинги.** Файл данных RefactoringMiner на commit `136ee7da5a3a13e10bea2ca8f4f8342f3fd40c98`; его SHA-256 и URL находятся в `anchors/source-lock.json`. Подготовщик получает bare-репозитории dit/dit, asyml/texar и kkroening/ffmpeg-python. Старые и новые Git SHA перечислены в queries, transfer-queries и reverse-queries. Этапы основной серии запускаются в каталоге anchors в порядке prepare.py, predict.py, score.py, route.py, identity.py. У дополнительных переносов `transfer.py` и `reverse.py` операции `prepare`, `predict`, `score` вызываются раздельно. [Аннотации на точной ревизии](https://github.com/tsantalis/RefactoringMiner/blob/136ee7da5a3a13e10bea2ca8f4f8342f3fd40c98/src/test/resources/oracle/python-dataset/data.json)
- **Исторические траектории.** В состав R8 включена обработанная адресная проекция и список входных хешей. Для получения проекции из исходных траекторий нужны прошлые R7 search/followup, R6 version/external и R5 writer/action_transfer/action_probe. Первичные траектории представлены в публичном хранилище отправок SWE-bench. Предыдущие receipts задают конкретные URL по задачам. Список и версии подсетов следует переносить из этих manifests, поскольку состав лидерборда меняется. [Артефакты отправок SWE-bench](https://github.com/swe-bench/experiments)
- **Локализация.** Авторские корпуса SWE-bench Lite function и Loc-Bench function поставляются в архиве, URL которого записан в `retrieval/acquire.py`. Получение основано на HTTP Range и предполагает тот же бинарный ZIP. Официальные веса SweRankEmbed-Small зафиксированы на `745d2a06103a66d3cfa600aa52fc0d3523010daa`, код энкодера на `92d97331f1f4b6a366c1f161354b9f3390cc219f`. Контрольные суммы — в model_manifest.json и backend_manifest.json. Скрипты используют Python, requests, NumPy, PyTorch, transformers и safetensors. Путь к локальному кешу задаётся переменной SWERANK_TEMP. [Официальный код SweRank](https://github.com/SalesforceAIResearch/SweRank/tree/d3df5088485eda13c7eebfcd6250052fd276f1a3) · [Веса](https://huggingface.co/Salesforce/SweRankEmbed-Small/tree/745d2a06103a66d3cfa600aa52fc0d3523010daa) · [Код энкодера](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-long/tree/92d97331f1f4b6a366c1f161354b9f3390cc219f)
- **Агент и исполнимые тесты.** Старый `graph_memory_round6/repair/transfer/collect_tasks.py` использует фиксированный Parquet SWE-bench Verified, сохраняет публичную задачу, gold patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS, затем получает репозиторий SymPy из codeload.github.com/sympy/sympy/tar.gz/ по базовому SHA. Каждый включённый public_input.json.gz содержит base и сведения о checkout. Для запуска исходного harness нужны прежние `repair/transfer`, `graph_memory_round7/reader` и `work/memory_session5/live/tokenizer.json`. Сервер использовал llama.cpp b12441 (commit `164ab018f9b7368ff8122094994c4b74e468aa0e`), Qwen3.8-27B-UD-Q4_K_M.gguf, SHA-256 `1bce504dfecd84153666928a41d8a66706f0158d3a317bc5196b72819d7dc529`. Командные параметры зафиксированы в launch.json и start_server.ps1 каждой серии. Целевые версии CUDA и артефакты рантайма перечислены в прежнем runtime_receipt.json. [Датасет](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified) · [Модель на зафиксированной ревизии](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/tree/4af51b3542f775b0a8e4b310bfb3f17e01c306c9) · [Версия llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/b12441)

Файлы с исходными ответами, параметрами генерации и техническими записями сохраняют исходные временные метки для аудита. В архив не включаются полные деревья checkout, агрегированный кеш авторских корпусов, зеркала Git, окружения Python, системные server.stdout/stderr и бинарные веса. Эти зависимости нужны в разной степени: для пересчёта агрегатов из включённых ответов и для повторной генерации полный объём требований различается.
