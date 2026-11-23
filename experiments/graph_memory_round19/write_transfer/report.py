"""Create a self-contained comparison including both transfer successes and the reversal against unbounded storage."""
from statistics import mean
from transfer import D,UP,load,put,pilot,measure
def record():
    rows=load("outcomes.json.gz");test=load(UP/"outcomes.json.gz")
    cohort={r["q"]:r for r in load("cohort.json")}
    outcomes={"dev580":rows,"profile500":[r for r in rows if cohort[r["q"]]["publication_dev500"]],"other80":[r for r in rows if not cohort[r["q"]]["publication_dev500"]],"previous_test2000":test}
    pairs=(("head/8192","fifo/8192"),("output_head/8192","head/8192"),("output_head/8192","all"),("shared","shifted"))
    paired={}
    for label,rr in outcomes.items():
        paired[label]={}
        for left,right in pairs:
            if left not in rr[0]["a"]:continue
            for k,stage in ((0,"write"),(3,"read")):
                diff=[r["a"][left][k]-r["a"][right][k] for r in rr]
                paired[label][f"{left}:{right}:{stage}"]={"wins":sum(x>0 for x in diff),"losses":sum(x<0 for x in diff),
                 "ties":sum(x==0 for x in diff),"delta_ci95":measure.ci(rr,(left,right),k)}
    put("pair-counts.json",paired)
    d=load("results.json");allm=d["all580"];old=load(UP/"results.json")["summary"];prior_graph=load(UP/"graph-results.json")["all"]["means"]
    put("previous-comparison.json",{"prior_source_hashes":{f:pilot.sha(UP/f) for f in ("results.json","graph-results.json","outcomes.json.gz")},
                                  "n":len(test),"counts":{**{p:[int(old[p]["write_count"]),int(old[p]["read_count"])] for p in ("all","head/8192","ends/8192","fifo/8192","output_head/8192","hash/8192")},
                                                         **{p:[round(prior_graph[p][0]*2000),round(prior_graph[p][3]*2000)] for p in ("shared","shifted")}}})
    notes=["# Перенос ограниченной записи памяти на development split ISETrace","",
           "Сохранение начала каждого события подтвердило преимущество над FIFO на всех 580 новых вопросах. Дополнительный приоритет начал результатов вызовов дал 255 полных комплектов свидетельств после чтения BM25 против 242 при одинаковом приоритете начал аргументов и результатов. Связать приоритеты двух сторон одним идентификатором вызова оказалось недостаточно для дополнительного выигрыша. Все правила использованы в версии, зафиксированной до получения этой выборки.",
           "", "| Политика | Dev. Сохранено / 580 | Dev. Прочитано / 580 | Средняя запись / траекторию, E5-токены | Среднее чтение / вопрос, E5-токены | Test. Сохранено / 2 000 | Test. Прочитано / 2 000 |","|---|---:|---:|---:|---:|---:|---:|"]
    prev=load("previous-comparison.json")["counts"]
    for k,name in (("fifo/8192","FIFO"),("hash/8192","Хеш отдельного блока"),("head/8192","Начало каждого события"),("ends/8192","Начало и конец"),("output_head/8192","Приоритет начала результатов"),("shared","Общий ключ вызова"),("shifted","Ключ предыдущего вызова"),("all","Полное хранение")):
        m=allm["metrics"][k];storage=allm["storage_per_trajectory"][k]
        notes.append((f"| {name} | {m['write_full_count']} | {m['read_full_count']} | {storage['write_tokens']:.1f} | {m['mean'][6]:.1f} | {prev[k][0]} | {prev[k][1]} |").replace(".",","))
    notes.extend(["","В колонках хранения измеряется, остались ли в памяти все эталонные символы по правильным адресам. Чтение BM25 по сохранённым данным ограничено 2 048 E5-токенами. У ограниченных методов ёмкость записи равна 8 192 токенам, служебные адреса в этот лимит не входят. Стоимость текста в UTF-8 и число блоков для каждой траектории доступны в [журнале хранения](storage.json.gz). Полное хранение соответствует другим затратам, поэтому служит точкой отсчёта по доступности данных. Метрика чтения характеризует найденные координаты доказательств.",
                  "","| Сравнение на dev | Стадия | Выигрыши / потери | Δ, п.п. [95% кластерный ДИ] |","|---|---|---:|---:|"])
    for a,b,title in (("head/8192","fifo/8192","Начала против FIFO"),("output_head/8192","head/8192","Приоритет результатов против обычных начал"),("shared","shifted","Общий ключ против смещённого"),("output_head/8192","all","Приоритет результатов против полного хранения")):
        for stage,sname in (("write","Запись"),("read","Чтение")):
            stat=paired["dev580"][f"{a}:{b}:{stage}"];dv,lo,hi=stat["delta_ci95"]
            notes.append((f"| {title} | {sname} | {stat['wins']} / {stat['losses']} | {100*dv:+.2f} [{100*lo:+.2f} … {100*hi:+.2f}] |").replace(".",","))
    notes.extend(["","**Какая часть эффекта переносится.** В более ранней тестовой выборке приоритет начала результатов после BM25 дал 873/2 000 против 831/2 000 при полном хранении. На dev порядок изменился: 255/580 против 258/580. Экономия хранения сохранилась (в среднем 7 868 против 36 582 токенов на траекторию). Превосходство над неограниченным хранением по качеству чтения не воспроизводится. [Парные сравнения в обеих выборках](pair-counts.json)",
                  "","| Подмножество dev | Запросов | FIFO запись / чтение | Начало запись / чтение | Приоритет результатов запись / чтение | Полное хранение запись / чтение |","|---|---:|---:|---:|---:|---:|"])
    for part,title in (("profile500","Публикационный профиль"),("other80","Оставшиеся вопросы")):
        g=d[part];m=g["metrics"]
        notes.append(f"| {title} | {g['n']} | "+" | ".join(f"{m[k]['write_full_count']} / {m[k]['read_full_count']}" for k in ("fifo/8192","head/8192","output_head/8192","all"))+" |")
    notes.extend(["","**Происхождение и независимость.** Публикационный профиль DenseFT использует 500 вопросов на 331 траектории для выбора чекпойнта. Ещё 80 вопросов принадлежат 74 траекториям. Между этими двумя срезами есть общие траектории. Все 352 траектории dev и все 580 запросов не пересекаются ни с 1 207 траекториями / 2 000 вопросами test, ни с train. Исходные агрегаты test были известны, а метод был разработан до нового dev-прогона. Это проверка переноса внутри одного корпуса. Ни один из восьми вариантов не обучается по dev-меткам. [Протокол](PROTOCOL_RU.md) · [Проверка исходного split](split-audit.json)",
                  "","Каждый из 4 640 исходов query×policy на двух стадиях пересчитан штатным span-оценщиком с исходными координатами. Файлы прогнозов сохранены до извлечения координат эталона. Каждый вопрос учитывается один раз на политику. Интервалы рассчитываются по траекториям, 10 000 выборок. [Полные метрики](results.json) · [Стандартная проверка и воспроизведение](REPRODUCE_RU.md)"])
    (D/"REPORT_RU.md").write_text("\n".join(notes)+"\n",encoding="utf8",newline="\n")
    files=sorted(p for p in D.rglob("*") if p.is_file() and p.name!="MANIFEST_SHA256.json" and "__pycache__" not in p.parts)
    put("MANIFEST_SHA256.json",{p.relative_to(D).as_posix():pilot.sha(p) for p in files})
    print(len(files),sum(p.stat().st_size for p in files),pilot.sha(D/"MANIFEST_SHA256.json"))
if __name__=="__main__":record()
