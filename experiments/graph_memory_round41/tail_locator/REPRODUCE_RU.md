# Проверка и воспроизведение

В архивных результатах находятся только хеши, размеры, типы запросов, адреса и счётчики. Переносимые проверки (хеши всех файлов, структуры панелей, исходов по каждому чтению, основные агрегаты и явные контрпримеры) используют стандартный Python.

~~~console
python -B verify.py
python -B locator.py
~~~

Для пересчёта по исходным данным нужен Python с pyarrow и NumPy. Сохраните расположение work/graph_memory_round41/tail_locator с доступными подписанными сериями graph_memory_round37, graph_memory_round38 и graph_memory_round40 и локальными Parquet-файлами Handoff Debt в D:/CodexResearch/x20-r31-handoff. Версия списка исходных шардов закреплена в panel-seal.json. Сверяйте recompute в отдельной копии с теми же локальными зависимостями. Запись существующих вычисленных файлов допускается только при точном совпадении байтов.

~~~console
python -B source.py
python -B evaluate.py
python -B analyze.py
python -B verify_raw.py
python -B verify.py
~~~

source.py фиксирует панель и отображённые хеши до использования before. Контрольные суммы кода зафиксированы в panel-seal.json и method-seal.json. evaluate.py создаёт временный файл с буквальными байтами снимка и исполняет операции seek/read с учётом фактически возвращённых байтов. verify_raw.py отдельно декодирует весь архивный просмотр и проверяет исходные строки непосредственным байтовым сравнением. [Точная ревизия корпуса](https://huggingface.co/datasets/kc-academy/handoff-debt/tree/79244eedc9d58349da0fcf1a2e05916e0ac5af00)
