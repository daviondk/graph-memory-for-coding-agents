"""Build the requested Russian archive-verification page with literal results from the lock."""
from report import *
def main():
    d=read("archive_results")
    h=read("full_results")
    paper_j=[.1658,.4849,.0784,.2083,.3280];best=[.2009,.5391,.1307,.3128,.4452]
    j=five(d,"jaccard");g=five(d,"graph");o=five(d,"owner")
    delta=[round((i-k)*100,4) for i,k in zip(j,paper_j)]
    match=sum(round(x*100,2)==round(y*100,2) for x,y in zip(j,paper_j))
    fmt=lambda a:" | ".join(pct(x) for x in a)
    gap=", ".join(f"{x:+.2f}".replace(".",",") for x in delta)
    ci_=d["all"]["paired"]["owner"]
    lead="Скачали исходный Java-набор, на котором авторы RepoBench опубликовали таблицу 2 в ICLR 2024. Граф оценён с теми же замороженными весами, что и на предыдущих страницах."
    body="В архиве 36 000 запросов из 349 проектов. На каждом уровне сложности 12 000 первых обращений и 6 000 повторных. С данными обучения и проверенными ранее 24 000 задач Hugging Face нет общих репозиториев или полных префиксов кода. Во всех методах сохраняются последние три строки по правилам авторов. Столбцы показывают процент попаданий правильного фрагмента среди первых 1, 3 или 5 кандидатов."
    positive="Оригинальный Jaccard совпал со статьёй во всех пяти столбцах при округлении до сотых. "+("Граф превысил каждый из пяти опубликованных максимумов." if all(x>y for x,y in zip(g,best)) else "Граф превысил "+str(sum(x>y for x,y in zip(g,best)))+" из пяти максимумов.")
    negative=f"Лексический контроль совпал в {match} из пяти столбцов. Расхождения по порядку столбцов составили {gap} п.п. Поэтому значения из статьи служат внешним ориентиром."
    end=f"На всём архиве прибавка графа относительно одинаково обученного контроля по первому месту составила {pct(ci_['delta'][0])} п.п., 95% ДИ {ci(ci_)}. При первом обращении прирост составил 1,26 п.п., при повторном 1,74 п.п. Ранжировщики графа и контроля видели 5 000 размеченных Java-задач из других репозиториев. Опубликованные модели применялись без такого обучения. Максимум в первом столбце принадлежит CodeGen, в остальных — InstructOR. Это сравнение с моделями конкретной таблицы."
    lines=["# Проверка на исходном архиве RepoBench","> "+lead,body,"@ 5.2 2.2 2.2 2.2 2.2 2.2","| Метод | Easy @1 | Easy @3 | Hard @1 | Hard @3 | Hard @5 |",f"| Jaccard, наш прогон | {fmt(j)} |",f"| Jaccard, статья | {fmt(paper_j)} |",f"| Контроль с предысторией | {fmt(o)} |",f"| Наш граф | {fmt(g)} |",f"| Максимум таблицы ICLR | {fmt(best)} |",positive if match==5 else negative,end,"~ [Статья и таблица 2, ICLR](https://proceedings.iclr.cc/paper_files/paper/2024/file/d191ba4c8923ed8fd8935b7c98658b5f-Paper-Conference.pdf) · [Исходный код и архив теста](https://github.com/Leolty/repobench/tree/ccacd12a68783ca27e9997c3b754d3e9e0d958da)"]
    (D.parent/"report/pages/03a-archive.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    (D/"archive_comparison.json").write_text(json.dumps({"paper_metrics":["easy@1","easy@3","hard@1","hard@3","hard@5"],"published_jaccard":paper_j,"observed_jaccard":j,"published_best_per_column":best,"observed_graph":g,"observed_owner":o,"matched_jaccard":match,"observed_minus_published_jaccard_pp":delta},indent=2),encoding="utf8")
if __name__=="__main__":main()
