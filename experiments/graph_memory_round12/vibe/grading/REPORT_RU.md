# Результаты штатного оценщика VibeMemBench

Готовы 10 из 10 записей. Для каждой сохранён точный SHA-256 поданной строки патча. Числа F2P и потерь P2P показываются только для фактически исполнявшихся тестов.

| Задача | Условие | Результат | Патч, Б | Прошли F2P | Потеряны P2P | Журнал |
|---|---|---|---:|---:|---:|---|
| adamchainz__flake8-comprehensions-553 | gold | решено | 5580 | 1/1 | 0/102 | [выход](controls/adamchainz__flake8-comprehensions-553/gold/unit.log) |
| adamchainz__flake8-comprehensions-553 | marker | не решено | 158 | 0/1 | 0/102 | [выход](controls/adamchainz__flake8-comprehensions-553/marker/unit.log) |
| mpmath__mpmath-881 | gold | решено | 2688 | 1/1 | 0/11 | [выход](controls/mpmath__mpmath-881/gold/unit.log) |
| mpmath__mpmath-881 | marker | не решено | 158 | 0/1 | 0/11 | [выход](controls/mpmath__mpmath-881/marker/unit.log) |
| adamchainz__flake8-comprehensions-553 | base | не решено | 2515 | 0/1 | 1/102 | [выход](models/adamchainz__flake8-comprehensions-553/base/unit.log) |
| adamchainz__flake8-comprehensions-553 | graph | пустая правка | 0 | — | — | [выход](models/adamchainz__flake8-comprehensions-553/graph/eval_stdout.log) |
| adamchainz__flake8-comprehensions-553 | raw | пустая правка | 0 | — | — | [выход](models/adamchainz__flake8-comprehensions-553/raw/eval_stdout.log) |
| mpmath__mpmath-881 | base | пустая правка | 0 | — | — | [выход](models/mpmath__mpmath-881/base/eval_stdout.log) |
| mpmath__mpmath-881 | graph | пустая правка | 0 | — | — | [выход](models/mpmath__mpmath-881/graph/eval_stdout.log) |
| mpmath__mpmath-881 | raw | пустая правка | 0 | — | — | [выход](models/mpmath__mpmath-881/raw/eval_stdout.log) |

| Условие решателя | Решено | Правка непуста | Фактический запуск тестов |
|---|---:|---:|---:|
| base | 0/2 | 1/2 | 1/2 |
| raw | 0/2 | 0/2 | 0/2 |
| graph | 0/2 | 0/2 | 0/2 |

При пустой правке нативный vendor завершает обработку записи до Docker. Список потерянных P2P, который отчёт по умолчанию заполняет в этой ветке, не является наблюдаемым провалом тестов. Для причин и статуса на уровне тестов см. построчные записи. [JSON со статусами](results.json) · [Окружение](environment.json) · [Воспроизведение](README_RU.md)
