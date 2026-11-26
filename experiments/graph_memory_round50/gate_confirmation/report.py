from paths_a import *

def num(x,digits=2):
    return f"{x:.{digits}f}".replace(".",",")

def main():
    res=get(D/"results.json");all_=res["groups"]["all"];p=all_["contrasts"]["adaptive-dense"];always=all_["contrasts"]["linked_dense-dense"]
    oldsig=get(D/"signflip-old.json");newsig=get(D/"signflip-new.json");orders=get(D/"orders.json.gz");panel=get(D/"panel.json")
    thresholds=get(D/"threshold-seal.json");bonus=get(D/"bonus-results.json")["summary"];emb=get(D/"embedding-cost.json")
    answers=get(D/"answer-seal.json");read=get(D/"reader-boundaries.json")
    def contrast(c,j=1):return num(c["pp"][j])+" ["+"; ".join(map(num,c["cluster_ci"][j]))+"]"
    def pvalue(v):return num(v,6)
    def sig_text(s):
        lab="точных перестановок знаков" if s["method"]=="exact" else "случайных перестановок знаков с поправкой +1"
        return f'{s["extreme"]:,} из {s["draws"]:,} {lab}, двустороннее p = {pvalue(s["two_sided_p"])}'
    def switches(arm):return sum(r[arm]!=r["dense"] for r in orders.values())
    ci=p["cluster_ci"][1]
    interpretation=("Результат воспроизводит положительную среднюю прибавку на новой панели." if ci[0]>0 and newsig["two_sided_p"]<.05 else
                    "Подтверждающий прогон указывает на снижение F1 при таком пороге." if ci[1]<0 and newsig["two_sided_p"]<.05 else
                    "Этот прогон не подтвердил положительную прибавку с заранее заданным порогом.")
    txt=["# Подтверждающая проверка фиксированного порога на 1 280 новых вопросах","",
      f'При пороге 0,04178261756896973 ридер получил **{num(100*all_["means"]["adaptive"][1])} Answer F1**, при свободном семантическом выборе — **{num(100*all_["means"]["dense"][1])}**. Единственная первичная парная разность **{contrast(p)} п.п.** {interpretation} Сменился второй источник у {switches("adaptive")} из 1 280 вопросов. F1 вырос в {newsig["wins"]}, снизился в {newsig["losses"]}, совпал в {newsig["n"]-newsig["k"]}. [Протокол](./PROTOCOL_RU.md) · [Результаты](./results.json)',"",
      "| Правило выбора | Смены относительно dense | Официальный Answer F1 | Официальный EM, % | Найдены все опорные заголовки, % | Средняя доля опор, % |",
      "|---|---:|---:|---:|---:|---:|"]
    for key,title in [("dense","Свободный dense"),("adaptive","Заранее фиксированный порог"),("linked_dense","Всегда предпочитать упомянутый, описательно")]:
        m=all_["means"][key];off=res["official"][key]
        txt.append("| "+title+" | "+str(switches(key))+" | "+" | ".join(num(v) for v in [off["f1"],off["em"],100*m[2],100*m[4]])+" |")
    txt+=["",f'Новая панель содержит {newsig["k"]} ненулевых пар F1. Дополнительная проверка по абсолютным величинам разностей дала {sig_text(newsig)}. У прежних 640 вопросов при том же пороге найдено {oldsig["wins"]} улучшений и {oldsig["losses"]} ухудшения, прежняя разность +0,64 п.п. [0,12; 1,29]. Для тех восьми ненулевых пар отдельно получено {sig_text(oldsig)}. Проверка случайной сменой знаков сохраняет величину каждой разности. Процентильные интервалы получены 10 000 парными перевыборками первых документов на каждой панели. [Новые парные разности](./signflip-new.json) · [Отдельная проверка прежней панели](./signflip-old.json)',"",
      f'Первичный эффект на полном покрытии опорных заголовков составляет {contrast(p,2)} п.п. При обязательном предпочтении упомянутого вторичная описательная разность F1 равна {contrast(always)} п.п. Оба сравнения относятся к одинаковым двум чтениям Qwen3-4B-Instruct-2507 Q4_K_M и адресным векторам Qwen3-Embedding-8B Q4_K_M. [Адреса и косинусы](./orders.json.gz) · [Оценки каждого вопроса](./outcomes.json.gz)',"",
      "### Эквивалентное правило с надбавкой","",
      f'Для каждого видимого ребра можно прибавить к косинусу его кандидата одну и ту же константу t. Аргумент максимума совпадает с правилом порога: добавление одной константы сохраняет порядок внутри каждого множества, а лучший упомянутый выигрывает у свободного лидера точно при отрыве ≤ t. На равенстве между множествами приоритет имеет упомянутый, внутри множества действует прежний порядок. Независимый пересчёт всех кандидатов как с binary64, так и с точными двоичными рациональными числами дал совпадение {bonus["original_fit"]["all_same"]}/640 при подборе и {bonus["confirmation"]["all_same"]}/1 280 в подтверждении. Число различающихся адресов с отрывом в точности t составило {bonus["original_fit"]["boundary_ties"]} и {bonus["confirmation"]["boundary_ties"]}. Это одна фиксированная надбавка к наблюдаемой поддержке. [Проверка эквивалентности](./bonus-results.json)',"",
      "### Происхождение и цена","",
      f'Первая страница каждого нового вопроса отличается от всех исторических каталожных страниц по точной паре заголовок+текст. Исключены прежние обе 640-вопросные панели, 2Wiki dev, HotpotQA validation и MuSiQue train/dev по ID и полным нормализованным вопросам. После исключения {panel["excluded_id"]} старых ID и {panel["excluded_question"]} дополнительных нормализованных совпадений рассмотрено {panel["examined"]} записей по хешу, чтобы выбрать 1 280. Отклонены {panel["rejected"]["first_in_prior_catalog"]} исторических первых страниц и {panel["rejected"]["duplicate_selected_first"]} повторов внутри нового набора. Прочие абзацы пересекались у {panel["pooled_catalogs_sharing"]} новых каталогов. Неизвестно, использовались ли публичные примеры в предобучении. Проверка относится к проектному holdout публичного train. [Панель](./panel.json) · [Хеши пересечений](./novelty.json.gz)',"",
      f'Адресатор обработал {emb["titles"]["unique"]} уникальных заголовков ({emb["titles"]["logical"]} логических обращений) и {emb["queries"]["unique"]} запросов за {num(emb["process_seconds"])} с вместе с запуском на RTX 3090. Каждая ветвь получила {read["prompt_tokens"]} входных токенов, из них {read["first_tokens"]} токенов первого фрагмента и {read["second_tokens"]} второго. Для 3 840 назначений было достаточно {answers["unique"]} свежих уникальных входов и 32 повторов за {num(answers["seconds"])} с. Расхождений в повторах — {answers["different"]}. [Затраты ридера](./costs.json) · [Затраты энкодера](./embedding-cost.json) · [Воспроизведение](./REPRODUCE_RU.md)']
    txt.extend(["","В предыдущих процедурах отбора весь train технически сканировался по ID и нормализованному вопросу для удаления дублей. Для новых 1 280 ни предшествующие панели Qwen, ни процедура подбора порога не содержали ответов ридера и золотых исходов. Правило оценки задано до запуска этих вопросов."])
    (D/"REPORT_RU.md").write_bytes(("\n".join(txt)+"\n").encode())
if __name__=="__main__":main()
