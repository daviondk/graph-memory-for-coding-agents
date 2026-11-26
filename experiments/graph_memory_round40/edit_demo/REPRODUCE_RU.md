# Запуск

Распакуйте архив и выполните команды в каталоге с app.py. Они используют только стандартную библиотеку Python, SQLite доступен в стандартной сборке.

~~~console
python -B verify.py
python -B app.py --port 8774
~~~

Откройте указанный адрес на 127.0.0.1. Меню Recorded edit переключает три сценария. В таблице видны адреса до и после правки для каждого блока. Выберите All observed blocks для просмотра всех кандидатов. Нажмите Verify line hashes and byte addresses, чтобы независимо сопоставить строки с обеими полными версиями, затем выберите блок для просмотра троек хешей. В примере Stale observation кнопка Inspect a stale selected line открывает свидетельство о прежнем расхождении. Все операции чтения локальны. При старте используются только анонимные локальные метаданные. [Первичный набор, закреплённая ревизия](https://huggingface.co/datasets/kc-academy/handoff-debt/tree/79244eedc9d58349da0fcf1a2e05916e0ac5af00)

Для повторения браузерного теста понадобится установленный Chromium и Python Playwright. Переменная BROWSER_EXE задаёт путь к браузеру. Можно сохранить снимок в новый файл.

~~~console
python -B browser_check.py --screenshot new-screenshot.png
~~~

Полное воспроизведение исходного извлечения требует рабочую структуру graph_memory_round40/edit_demo с соседними span_updates, natural_invalidations, graph_memory_round38/edit_ready и исходными Parquet-файлами Handoff Debt согласно snapshot-манифесту. Сборщик проверяет подписи, сопоставляет исходные и последующие полные версии только трёх выбранных квитанций, хеширует строки, сверяет с агрегатами независимого строгого аудита. Результаты записываются по одному разу в новые файлы.

~~~console
python -B choose.py
python -B build.py --corpus D:/CodexResearch/x20-r31-handoff --out fresh-projection
~~~

Сборщик использует pyarrow для чтения Parquet. Воспроизводимость двух SQLite-файлов и source-bindings.json проверена побайтно на указанной локальной сборке. Иные версии SQLite могут дать другой файловый формат при тех же логических данных.
