"""Create a per-folder source diagnostic."""
import collections
import gzip
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(name):
    raw=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)
selection=read("selection.json")
summary=read("summary.json")
records=read("records.json.gz")
unknown_models=collections.Counter(row["folder"] for row in records if row["model_name"] is None)
schema_counts=collections.Counter(tuple(row["schema"]["info_keys"]) for row in records)
different=[row for row in records if row["comparison"]["bytes_equal_nonempty"] is False]
nonpatch=[row for row in records if row["comparison"]["both_nonempty"] and row["comparison"]["git_patch_id_equal"] is None]
layouts={}
for folder in selection["folders"]:
    inventory=read("inventory/"+folder["folder"]+".json.gz")
    objects=inventory["listing"]["objects"]
    layouts[folder["folder"]]={"relative_top_levels":dict(collections.Counter(obj["key"].removeprefix("bash-only/"+folder["folder"]+"/").split("/")[0] for obj in objects)),
      "object_count":len(objects),"patch_count":folder["patch_count"],"trace_count":folder["trace_count"],
      "paired":folder["intersection_count"],"patch_only_ids":folder["patch_only_ids"],
      "trace_only_ids":folder["trace_only_ids"],"other_layout":folder["other_layout"]}
diagnostics={"layouts":layouts,"unknown_models":dict(unknown_models),
  "info_schemas":[{"keys":list(keys),"count":count} for keys,count in sorted(schema_counts.items())],
  "nonempty_unsigned_pairs":[{"folder":row["folder"],"id":row["id"],"byte_same":row["comparison"]["bytes_equal_nonempty"]} for row in nonpatch],
  "different_pairs":[{"folder":row["folder"],"id":row["id"],"comparison":row["comparison"],"trace":row["trace"],"patch":row["patch"]} for row in different],
  "fetched_bytes":sum(row["trace"]["bytes"]+row["patch"]["bytes"] for row in records),
  "md5_verified_objects":sum(row[key]["md5_verified"] for row in records for key in ("trace","patch"))}
(ROOT/"diagnostics.json").write_text(json.dumps(diagnostics,ensure_ascii=True,indent=2))
text="""# Независимая проверка соответствия траектории и оцениваемого патча

## Наблюдение

Полный census публичного S3 раздела bash-only выявил 55 папок. В 54 именах присутствует mini. После исключения трёх исходных anchor submissions, два из которых найдены в данном listing, осталось 52 новые папки. В 41 папке доступны пары патч и траектория. В каждой выбраны 24 issue по заранее установленному salted SHA256. Итого проверено 984 пары. Все 1 968 объектов успешно получены и сверены с размером и ETag из listing. Для всех выполнена проверка MD5 по односоставному ETag. Суммарно прочитано 338 564 937 bytes.

Из 948 пар с непустыми строками с обеих сторон 945 совпали побайтно, 3 различались. Во всех трёх случаях папка одна, 20250807_mini-v1.7.0_gpt-oss-120b. В двух случаях различаются строки изменений по файлам и успешные Git patch-id. Для третьего info.submission содержит строку ошибки RetryError и успешная подпись патча отсутствует.

Среди 923 непустых пар с успешными Git-подписями совпала 921, различались 2. Доля расхождений составляет 2/923 или 0,217% в этой выборке. Для побайтного сравнения это 3/948 или 0,316%. Эти доли относятся к фиксированной выборке с равным числом примеров на папку. Кластер расхождений — 1 из 41 доступной папки.

36 пар пусты с обеих сторон. У 25 непустых пар отсутствует сопоставимая Git-подпись, из них 24 побайтно одинаковы. Эти случаи учтены отдельной категорией. Все 984 траектории содержат строковое info.submission. Поле info.config.model.model_name есть у 672 записей. В 312 записях из 13 старых папок отсутствует config-секция. Модель из имени папки не подставлялась.

Этот независимый корпус подтверждает существование расхождений между публичным финальным submission и evaluator patch. Большинство проверенных материалов совпадает. По этим данным нельзя установить корректность исправления, причину расхождения или ошибку leaderboard score. Test outcomes и содержимое report.json не запрашивались.

## Воспроизводимость

Протокол находится в соседнем EXTERNAL_PROTOCOL.md, копия также включена сюда. selection.json, 52 полных listing manifests и lock фиксируют корпус и выборку до чтения патчей. Изначальный path-parser учитывал прямой путь к траектории и вернул нулевое число пар. Затем по одним listing-метаданным добавлен стандартный вложенный путь trajs/{issue}/{issue}.traj.json. Этот шаг описан в SCHEMA_AMENDMENT.md, первоначальные код, selection и lock сохранены с суффиксом v1. Salt и число примеров сохранились.

audit.py inventory строит census и фиксирует выборку. audit.py audit загружает исключительно выбранные траектории и патчи, проверяет объектные receipts, извлекает строку submission и ограниченную проекцию config. Исходные траектории после обработки отброшены. Сохранены SHA256 исходного тела, URL, ETag, размер, timestamp, модель, SHA256 config и два патча.

Автономная проверка выполняется из этого каталога командой python -B verify.py. Нужен Python 3.10+ и стандартная библиотека. При наличии git verifier дополнительно пересчитывает patch-id. Проверяются выборка по полным manifests, все сохранённые SHA, побайтное совпадение, строки изменений и агрегированные количества. При отсутствии git пересчитываются все остальные проверки с явным сообщением. Исходное тело траектории локально не сохранено, поэтому автономно проверяется сохранённая проекция, а SHA/MD5 raw trace остаются receipts момента получения. Полная повторная сверка проекции с оригиналом требует HTTP-получения по сохранённым URL и SHA.

Локальные locks не являются внешней регистрацией протокола. Git patch-id игнорирует часть форматных различий. Signed-lines сравнение требует текстовых hunks и сохраняет порядок файлов и изменённых строк. Побайтное сравнение применяется к UTF-8 строке JSON submission и исходному evaluator patch. Пустые строки и неуспешные подписи исключены из соответствующих знаменателей.

## Все обследованные папки

| Папка | Доступные пары | Проверено | Побайтно равно | Побайтно различно | Пусто или unknown |
|---|---:|---:|---:|---:|---:|
"""
for folder in selection["folders"]:
    name=folder["folder"]
    stats=summary["folders"].get(name)
    if stats:
        byte=stats["bytes_equal_nonempty"]
        text+=f"| {name} | {folder['intersection_count']} | {stats['selected']} | {byte['equal']} | {byte['different']} | {byte['unknown_or_empty']} |\n"
    else:
        text+=f"| {name} | {folder.get('intersection_count',0)} | 0 | — | — | — |\n"
text+="\n## Недоступные пары и варианты схемы\n\n"
for folder in selection["folders"]:
    if not folder["selection"]:
        text+=f"- {folder['folder']}. Патчей {folder.get('patch_count',0)}, траекторий {folder.get('trace_count',0)}. Пересечение 0.\n"
text+="\nПолные списки отсутствующих идентификаторов и top-level layouts сохранены в diagnostics.json. В старых folders с нулём траекторий .traj.json может существовать иной формат архива. Расширение корпуса за пределы наблюдаемых отдельных объектов в этот протокол не входило.\n\n## Обнаруженные расхождения\n\n"
for row in different:
    c=row["comparison"]
    text+=f"- {row['folder']} / {row['id']}. Signed changes {c['signed_changes_equal']}, Git patch-id {c['git_patch_id_equal']}. [Evaluator patch]({row['patch']['url']}) и [trajectory]({row['trace']['url']}).\n"
text+="\n## Исходные модели отсутствуют в config\n\n"
for folder,count in sorted(unknown_models.items()):
    text+=f"- {folder}, {count} записей.\n"
text+="\n## Следствие для экспериментов памяти\n\nПеред связыванием action memory с результатом решения необходимо проверять идентичность опубликованного final artifact и артефакта, к которому относится оценка. Неподтверждённую связь следует сохранять как unknown с provenance. Этот аудит проверяет качество корпуса. Для проверки влияния provenance-aware памяти на агентное решение нужен отдельный контролируемый эксперимент.\n"
(ROOT/"summary_ru.md").write_text(text,encoding="utf8")
print("report written")

