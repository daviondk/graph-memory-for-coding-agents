# Воспроизведение

Используются Python 3.12.13, NumPy 2.5.5 и те же реализации graph_memory_round10/multiset, что в основном эксперименте. Соседняя папка graph_memory_round9/budget содержит sketch.py. Команда проверки готового пакета — python verify_quix.py. Она сверяет SHA-256, снимает точные маски прямо с нативных трасс и независимо агрегирует все 15 552 первичных состояния. Проверка SHA всех файлов пакета задаётся MANIFEST_SHA256.json.

Исходный QuixBugs зафиксирован на 4257f44b0ff1181dedaedee6a447e133219fcebf. В native_source_and_traces.json.gz сохранены все 36 файлов эксперимента: 18 исходников исследуемых ревизий и 18 нативных трейсов с тестовыми статусами. Распространение исходников сопровождается QuixBugs-LICENSE.txt. Обе версии даны именно с логическими ревизиями base/gold, использовавшимися в R9. Имена и полные последовательности исполнения доступны в trace.json.gz. Для сопоставления с исходным репозиторием используйте протокол R9 и метаданные native_inputs.json.

Для пересборки используйте пустую копию текущей рабочей папки с кодом, протоколами и native_source_and_traces.json.gz. У папок graph_memory_round9, graph_memory_round10 и graph_memory_round11 должен быть один родитель. Необязательно копировать чек-ауты с исходного диска: python native_archive.py --unpack <путь-к-новой-graph_memory_round9> восстановит только входные данные из квитанции. Скопируйте sketch.py в budget/ отдельным шагом. В graph_memory_round10/multiset нужны common.py, structures.py, reader.py, ef_build.py, ef_reader.py, ef_direct.py и grade.py, а для дополнительного контроля точного хранения SymPy — подкаталог old/. Старые сохранённые R9/R10 состояния перезаписывать не требуется.

    python project.py
    python qbuild.py
    python qread.py
    python qgrade.py
    python qtime.py
    python semantic.py
    python sympy_full.py
    python verify_quix.py

Состояния фиксируются до первого запроса; построитель проверяет отсутствие старого state_seal.json в целевой копии. Для контроля формата в states/ содержится плотная упаковка всех методов и солей в JSON с gzip. Число стоящих в бюджете байт относится к декодированной base64 строке. readouts.json.gz содержит отдельное предсказание и параметры каждого метода. semantic_rows.json.gz даёт аналогичные данные для дополнительного запроса. Порядок полей базовой строки чтения: task, direction, bytes per test, salt, method, selected mask, payload bytes, fitted parameters. Основной отчёт – REPORT_RU.md.
