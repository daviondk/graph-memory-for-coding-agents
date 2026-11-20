# Воспроизведение R3 чтения

Рабочая папка D:/CodexResearch/x20-bench-workspace/work/graph_memory_round3/context. Нужна соседняя graph_memory_round2 с обученными моделями и модулями span_memory и edit_memory, а также memory_session5/packets с обработчиками, Qwen-токенизатором и исходными обучающими шардaми. На диске D они сохранены по исходным адресам. Полный механизм, все ограничения и сравнения приведены в RESULTS_RU.md.

**Быстрая проверка.** Python 3.14.4, NumPy и tokenizers. Запускайте из отдельной рабочей копии: подготовительные скрипты перезаписывают производные файлы. Команда python audit.py сверяет исходные предсказания модели R2 с 88 авторскими контрольными сохранениями этого проекта, проверяет изоляцию датасетов, наличие старых строк и индивидуальные цены. python grade.py и python replicate.py grade пересчитают оценки по уже сохранённым предсказаниям и проекциям, с проверкой всех цен и хешей. python matched_grade.py проверяет индивидуальные лимиты, python expansion.py grade discovery и python expansion.py grade replication — расширение. Именованные группы discovery и replication обозначают два различных набора проектов. В журнал предсказаний не передаются будущие действия. Хеши в method_lock, prediction_lock и прочих lock.json относятся к исходной раскладке и данным.

**Полный повтор.** Для чтения исходных 8 parquet используется сохранённый pyarrow CPython 3.12 с import path из memory_session4/compact/.scratch/lib. В оригинальной раскладке сначала в таком окружении выполняются acquire.py и confirm_acquire.py. Можно использовать уже приложенные 16 безопасных проекций и пропустить эту загрузку. Источник и SHA256 каждого parquet в memory_session5/packets/shards.json, выбранные координаты в обеих selection.json. Основная подготовка на CPU далее идёт по фазам:

```powershell
python context.py
python predict.py
python grade.py
python derive_matched.py
python matched_policy.py
python matched_grade.py
python replicate.py predict
python replicate.py grade
python expansion.py predict discovery
python expansion.py predict replication
python expansion.py grade discovery
python expansion.py grade replication
python serializers.py discovery
python serializers.py replication
python targets.py
python cost_audit.py
python examples.py
python audit.py
```

Модель, входные проекции, формы параметров, предсказания на каждом срезе, суммы стоимости, интервалы и исходы каждого принятого действия сохранены под соответствующими именами, для второго набора в replication/. В журнале CPU сохранены средние маргинальные расходы с прогретым кэшем. Каждая таблица имеет машиночитаемый JSON-оригинал. Общее множество проектов и данные предыдущего R2-F, работавшие в роли контрольной системы, в статистику R3 повторно не добавлены.
