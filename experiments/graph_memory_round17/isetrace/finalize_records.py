"""Assemble a final manifest from completed, individually signed ranking and evaluation records."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
def load(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def num(x):return f"{x:.3f}".replace(".",",")
def ci(c):
    lo,hi=c["trajectory_bootstrap_ci"]
    return f"{100*c['delta']:+.1f} п.п. ({100*lo:+.1f}…{100*hi:+.1f})".replace(".",",").replace("п,п,","п.п.")
def persist(path,data):
    if isinstance(data,str):data=data.encode("utf8")
    if path.exists():assert path.read_bytes()==data,path
    else:path.write_bytes(data)
def checked(root,manifest):
    for n,h in manifest.items():
        p=root/n
        assert p.resolve().is_relative_to(root.resolve()) and sha(p)==h,n
def main():
    dense=ROOT/"dense";clip=ROOT/"truncation"
    for name in ("plan-seal.json","dense-predictions-seal.json"):checked(dense,load(dense/name))
    for scorer in ("bm25","dense"):checked(clip,load(clip/(scorer+"-seal.json")))
    initial=load(ROOT/"BM25_MANIFEST_SHA256.json")
    baseline=ROOT/"BM25_REPORT_RU.md";out=ROOT/"REPORT_RU.md"
    if not baseline.exists():
        assert sha(out)==initial["REPORT_RU.md"]
        shutil.copyfile(out,baseline)
    for n,h in initial.items():
        assert sha(baseline if n=="REPORT_RU.md" else ROOT/n)==h
    allscores=load(dense/"summary.json");scores=allscores["summaries"];delta=allscores["contrasts"]
    clipped=load(clip/"dense-results.json");runtime=load(dense/"runtime.json")
    report=["# Проверка упаковки с предобученным E5", "",
            "На восьми траекториях из каждого шарда сравнили две модели ранжирования одних и тех же фрагментов аргументов и результатов. Все 27 запросов (13 и 14) были отобраны до построения векторов. Кандидаты, исходные координаты, результаты базового BM25 и стоимость сначала поштучно сверены с основной серией. Для E5 использовались исходные процедуры Sentence Transformers и авторский DenseTaskRetriever с закреплёнными весами. [Зафиксированный протокол](PROTOCOL_RU.md) · [Идентификаторы](selection.json) · [Контрольные суммы весов](weights-lock.json)","","| Ранжирование и чтение | Полная поддержка I (13) | Полная поддержка II (14) | Всего (27) | Coverage | Density | Средний расход |","|---|---:|---:|---:|---:|---:|---:|"]
    names={"prefix":"штатный префикс","skip":"пропуск","value":"остаток по баллу / √токенов","related":"приоритет пары одного вызова"}
    for r,title in (("bm25","BM25"),("dense","E5")):
        for h,title_h in names.items():
            both=scores[f"all/{r}/2048/{h}"];a=scores[f"0/{r}/2048/{h}"];b=scores[f"1/{r}/2048/{h}"]
            report.append(f"| {title}, {title_h} | {a['full']} | {b['full']} | {both['full']} | {num(both['coverage'])} | {num(both['density'])} | {both['tokens']:.0f} |")
    result=delta["all/dense/2048/skip-prefix"];vs=delta["all/dense/2048/related-value"]
    report.extend(["",f"Для замороженного E5 пропуск относительно исходного префикса дал {result['wins']} выигрышей и {result['losses']} потерь, разница {ci(result)}. При сравнении приоритета пары с нормировкой по стоимости получили {vs['wins']} выигрышей и {vs['losses']} потерь, разница {ci(vs)}. Это парные описательные 95% интервалы по траекториям; в выборке 16 кластеров. [Полные показатели при трёх бюджетах](summary.json) · [Поштучные исходы](outcomes.json.gz)","",
        f"Дополнительное усечение первого не помещающегося элемента до оставшихся исходных токенов дало на E5 {clipped['0/2048']['clip']['full']}/13 и {clipped['1/2048']['clip']['full']}/14. Каждый запрос расходует полный предел 2 048. [Правило усечения](../truncation/PROTOCOL_RU.md) · [Парные сравнения с усечением](../truncation/dense-results.json)","",
        f"Точный E5-base-v2 (768 компонент) вычислил {runtime['encoded_unique_strings']} различных строк запроса и фрагмента с префиксами query и passage. Вызван авторский код нормировки и ранжирования по скалярному произведению. Использованы CPU float32, 6 потоков, torch {runtime['torch']}, transformers {runtime['transformers']} и sentence-transformers {runtime['sentence_transformers']}. Ранжирование завершённого запуска заняло {runtime['seconds']:.1f} с. Первое исполнение было прервано до фиксации результатов. В итог входит полностью завершённый повтор неизменённой замороженной выборки. Второй исполнитель сохранял только векторы точных входных строк для восстановления. [Версии и время](runtime.json) · [Обработка восстановления](resume_cpu.py)","",
        "Для пересчёта запустите score из dense.py, затем summary.py. Для получения исходных ранжирований нужны wget-эквивалент provision_e5.py, зафиксированный ранее снимок BM25 и конфигурация из протокола. После появления ранжирований выполните из папки truncation команды python -B clip.py rank dense и python -B clip.py score dense. Размер выборки исключает надёжное ранжирование близких политик; обучение Dense-FT и пяти отдельных R-GCN на полном протоколе авторов здесь не выполнялось. [Реализация GraphMemory](https://github.com/xiaoqi-7/GraphMemory)",""])
    persist(dense/"REPORT_RU.md","\n".join(report).replace("wget-эквивалент provision_e5.py","скрипт загрузки provision_e5.py"))
    dense_prefix=scores["all/dense/2048/prefix"]["full"];dense_skip=scores["all/dense/2048/skip"]["full"]
    index=f"""# Графовая память ISETrace при ограниченном контексте

На двух непересекающихся панелях проверены 204 запроса к памяти из 127 инструментальных траекторий. Когда очередное свидетельство целиком не помещалось, продолжение поиска более короткого фрагмента повысило число полных комплектов доказательств с **47 до 53 из 104** на первой панели и **с 37 до 42 из 100** на второй. Ранжирование — авторский BM25 по единицам происхождения, разрешённый бюджет — 2 048 токенов. В независимом повторении 95% кластерный интервал прибавки составил от +1,0 до +9,8 п.п. [Дизайн, метрики и происхождение](BM25_REPORT_RU.md)

| Как читалась память | Первая панель | Повторение |
|---|---:|---:|
| Штатный непрерывный префикс BM25 | 47/104 | 37/100 |
| Частичное чтение следующего узла до ровно 2 048 токенов | 47/104 | 39/100 |
| Пропуск не помещающихся и чтение следующих целых узлов | 53/104 | 42/100 |
| Ранжирование остатка по баллу BM25 / √стоимости | 58/104 | 43/100 |
| Приоритет аргумента или результата того же вызова | 58/104 | 42/100 |

Часть выигрыша обусловлена расходованием разрешённого объёма. В повторении штатный префикс расходовал в среднем 1 855 токенов, обычный пропуск — 2 043. Приоритет пары одного вызова проиграл простой нормировке стоимости на один запрос (3 выигрыша, 4 потери). Для проверки этой связи выборка содержала всего семь запросов, действительно требовавших аргумент и результат одного и того же вызова. [Равнобюджетный контроль](truncation/REPORT_RU.md) · [Разбор нескольких событий](EVENTS_RU.md)

На заранее выбранных 27 запросах тех же панелей повторили четыре правила с закреплённым **intfloat/e5-base-v2**. На штатном E5-префиксе полная поддержка составила **{dense_prefix}/27**, при пропуске — **{dense_skip}/27**. Суммирование, токенизация, проверки опорных координат и нативная оценка прослеживаются до отдельных запросов. Полная таблица сравнений с E5 и ограничение малой панели приведены в отдельном отчёте. [Предобученный ранжировщик и сравнения](dense/REPORT_RU.md)

Две панели построены из полных сырых событий первых двух шардов и проверенных ранних ID публичного корпуса. Точный состав авторского теста из 2 000 запросов по восьми шардам отдельно не восстанавливался. Это оценка наполнения контекста доказательствами в общих инструментальных задачах. Превосходство над обученной Residual R-GCN и влияние на решение задач программирования остаются открытыми. [Публикация и исходная постановка](https://arxiv.org/abs/2609.25913) · [Воспроизведение](REPRODUCE_RU.md)

Манифест BM25 сохраняет отпечатки первоначального отдельно переданного пакета. Его запись REPORT_RU.md соответствует сохранённой копии BM25_REPORT_RU.md. MANIFEST_SHA256.json охватывает окончательный пакет со всеми отчётами и проверками.
"""
    out.write_text(index,encoding="utf8",newline="\n")
    files=sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name!="MANIFEST_SHA256.json" and "__pycache__" not in p.parts)
    assert all(p.suffix in (".py",".md",".json",".gz") for p in files)
    payload={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    manifest=ROOT/"MANIFEST_SHA256.json";persist(manifest,json.dumps(payload,sort_keys=True,indent=2)+"\n")
    checked(ROOT,payload)
    print(len(payload),sum(f.stat().st_size for f in files),sha(manifest))
if __name__=="__main__":main()
