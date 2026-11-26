# Воспроизведение

Числовой архив проверяется одной командой `python -B verify.py` с NumPy. Он включает наблюдения для всех состояний и структурированные коэффициенты/интервалы по обоим интерфейсам.

Для полного пересчёта используются предыдущие подписанные каталоги [cache_admission](../../graph_memory_round48/cache_admission/REPORT_RU.md), [embedding_reuse](../../graph_memory_round48/embedding_reuse/REPORT_RU.md) и [long_gpu](../long_gpu/REPORT_RU.md). Внесённые SIEVE и S3-FIFO проверяются запуском оригинального кода на синтетических и фактических последовательностях. Загрузите исходники ревизии 5fa68ef6902350aa9734398862bec7912d59f5e3 из [архива авторов](https://github.com/1a1a11a/libCacheSim/archive/5fa68ef6902350aa9734398862bec7912d59f5e3.tar.gz). Команда `SOURCE=/path/to/checkout sh build_reference.sh` выполняется в Linux из этого каталога, с CMake, системами сборки C/C++, pkg-config и GLib development headers. По умолчанию исполняемый драйвер сохраняется как `/tmp/r49cache-reference`. Сравните SHA256 файлов Sieve.c и S3FIFO.c с полями [эталонной проверки](reference.json). Под Windows использовался локальный WSL CodexX20MSR; в обычном Linux вызовы происходят напрямую. Сеть не участвует в обработке данных.

```text
python -B reference_check.py
python -B experiment.py
python -B native_benchmark.py
python -B report.py
python -B verify.py
```

Программа native_benchmark подаёт в оригинальный кеш отдельные команды проверки наличия и обычного обращения. Отрицательная запись сбрасывает кеш или запрашивает read-only lookup без обновления; обычные неотрицательные идентификаторы запускают штатные функции S3FIFO_get/Sieve_get через интерфейс get. Адреса соответствуют внутренним идентификаторам токенов источника, затраты считаются с фактической длиной источника. Ни код из внешних репозиториев бенчмарка, ни тексты действий агентов не исполняются. Библиотека относится только к открытым реализациям кеша.

