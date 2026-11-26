# Воспроизведение

Эксперимент хранится рядом с R34 и R37 на диске D. Внешняя запись и пересылка предсказаний не требуются.

| Скрипт | Назначение |
|---|---|
| data.py | Наблюдаемые признаки состояния и отношений, обучение по допустимым сертификатам |
| fit.py | Две модели, выбор параметров на dev, фиксация полных предсказаний локальной test-части |
| grade.py | Независимый вызов официального score_prediction и парный bootstrap |
| supervision.py | Вторичные факторные контроли, фиксация и проверка на том же разбиении |
| verify.py | Автономная проверка хешей, идентификаторов и агрегатов без внешней разметки |

В командной строке PowerShell из этой папки, при наличии исходных кешей проекта и Python с NumPy, SciPy и scikit-learn:

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $runner -B fit.py
& $runner -B grade.py
& $runner -B supervision.py fit
& $runner -B supervision.py grade
& $runner -B verify.py
```

Исходные ограничения и порядок настройки зафиксированы в PROTOCOL_RU.md и SUPERVISION_RU.md. Основные исходы по каждому состоянию хранятся в outcomes.json.gz, списки выбранных идентификаторов — в predictions.json.gz. Для вторичных контролей сохранены прогнозы, параметры, bootstrap и агрегаты. Выходы каждого этапа фиксируются в seal.json, selection.json и supervision-seal.json. Итоговые отчёты и данные проверяются по manifest.json с SHA-256. Хеши не являются независимым внешним заверением времени.

Исходные кеши — graph_memory_round34/external_transfer/strong/features.json.gz, graph_memory_round37/serbench_reference/predictions.json.gz и outcomes.json.gz, а также memory_session5/serbench с dense_vectors.npy, выгрузкой Cal500 и авторской реализацией scorer. data.py использует относительные пути от корня work и векторы в порядке исходного пула. Закрытые расходы и ragged batching языковой модели не нужны. Если перезапускается полный эксперимент с иными версиями Python и библиотек, сначала зафиксируйте новое окружение и используйте отдельную копию каталога для сравнения хешей. Сохранённые таблицы и списки предсказаний можно проверять стандартной библиотекой Python без обучающего окружения.
