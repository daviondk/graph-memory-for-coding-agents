# Проверка и воспроизведение

Для независимой проверки замороженных меток A/L, SQL-счётчиков, суммарного времени и граничных вариантов восстановления упакованного заголовка требуется только Python с SQLite из стандартной библиотеки. Команда запускается в каталоге опыта.

~~~powershell
python verify.py
~~~

Для полного повтора используйте отдельную копию каталога на том же уровне диска D и сохраните структуру соседних серий R37. Среда эксперимента — Windows с Python 3.12 и NumPy; для циклов потока используется QueryThreadCycleTime.

~~~powershell
$pythonResearch='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $pythonResearch inputs.py
& $pythonResearch run.py
~~~

Перед вторичным измерением обновите контрольный отпечаток собственного первичного нового прогона:

~~~powershell
& $pythonResearch -c "from inputs import D,put,sha; put(D/'primary-seal.json',dict(raw=sha(D/'raw.json.gz'),run=sha(D/'run-seal.json'),plan=sha(D/'plan.json'),secondary_protocol=sha(D/'PACKED_ADDENDUM_RU.md')))"
& $pythonResearch run_packed.py
& $pythonResearch analyze.py
& $pythonResearch verify.py
~~~

В основном и дополнительном прогонах драйвер создаёт новые временные SQLite-базы в каталоге исследования и убирает их при завершении. Файлы prefixes.json.gz и schedule.json.gz раздельно содержат причинные входы и внешнее расписание последующих чтений; методы хранения не получают расписание при выборе плана. В results.json хранятся средние и исходы по каждому репозиторию, интервалы по задачам и репозиториям, циклы потока и SQL-счётчики. Маршруты и результаты должны остаться прежними; новые значения физического времени могут измениться.
