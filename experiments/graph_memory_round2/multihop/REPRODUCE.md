# Воспроизведение

Python 3.12, CPU. В среде опыта использованы NumPy 2.2.6, scikit-learn 1.7.2, SciPy и PyArrow. Точные версии зафиксированы рядом в `requirements.txt`. Около 0,45 ГБ общедоступных исходных данных плюс промежуточные матрицы в `cache/`. Число worker-процессов — 3, потоков BLAS/OpenMP — 2. SHA-256 повторно проверяются. Рабочий каталог — папка этого файла, например в копии раздаваемого пакета. При повторении выходы с теми же именами перезаписываются, именно поэтому рекомендуется отдельная копия. Команды для PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe fetch.py
.\.venv\Scripts\python.exe -B pipeline.py all
.\.venv\Scripts\python.exe -B transfer.py all
.\.venv\Scripts\python.exe -B verify.py
.\.venv\Scripts\python.exe -B typed.py all
.\.venv\Scripts\python.exe -B verify_typed.py
.\.venv\Scripts\python.exe -B audit_replication.py
```

Первый полный запуск создаёт числовой `cache/` и упорядоченные ID, повторно используемые в остальных опытах. В поставляемой рабочей копии для проверки уже скачанных файлов достаточно `python fetch.py --check-only`. Для повторной оценки зафиксированных предсказаний их хеши должны совпасть с lock-файлами. Параметр `grade` в `transfer.py` и `typed.py` только оценивает эти файлы. Скрипт `verify.py` независимо пересчитывает первые два этапа по официальным данным; отдельный скрипт `verify_typed.py` перепроверяет третий этап. Обучающие наборы и веса Beam не требуются, потому что его авторы уже опубликовали прогнозы по каждому ID.

Адреса исходных файлов с ревизиями перечислены в fetch.py. Формат бинарного gzip фиксирован, однако при иной платформе, версии библиотеки или числе потоков могут отличаться вычисления с плавающей запятой и время.
