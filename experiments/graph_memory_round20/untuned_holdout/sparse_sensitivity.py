"""Post hoc sparse-cluster sign sensitivity for held-out full-support differences."""
from collections import Counter
from math import comb
from validate_transfer import HERE,FACTOR,TYPED,read,write,digest
def main():
    outcome=FACTOR/"hash64-extra-outcomes.json.gz"
    rows=read(outcome);plan=read(TYPED/"source-plan.json");novel=set(plan["novel_trajectories"]);res={}
    for scope in ("all","new","shared"):
        change=Counter();q=0
        for k,x in rows["prefix/factor"].items():
            if scope!="all" and (x["t"] in novel)!=(scope=="new"):continue
            y=rows["prefix/dense"][k];assert x["t"]==y["t"]
            q+=1;change[x["t"]]+=int(x["full_support"]-y["full_support"])
        wins=sum(v>0 for v in change.values());losses=sum(v<0 for v in change.values());n=wins+losses
        p=min(1,2*sum(comb(n,j) for j in range(min(wins,losses)+1))/2**n) if n else 1.
        res[scope]={"questions":q,"clusters":len(change),"positive":wins,"negative":losses,"tie":len(change)-n,"net_questions":sum(change.values()),"two_sided_cluster_sign_p":p}
    write(HERE/"sparse-sign.json",{"panels":res,"outcomes":digest(outcome)})
    text=["# Чувствительность к малому числу траекторий",
          "Повторный анализ выполнен после вычисления результатов дополнительных 80 вопросов. В каждой траектории суммируем парные изменения Full Support факторизованного hash64-читателя относительно исходного префикса Dense. Для ненулевых сумм используем точный двусторонний знаковый тест с вероятностью положительного знака 1/2. Это другая статистическая гипотеза, чем сдвиг среднего числа полных источников в кластерном bootstrap. Оба расчёта описывают устойчивость направления при малом количестве изменённых траекторий.",
          "| Выборка | Вопросы / траектории | Положительных / отрицательных / без изменений | Точный двусторонний p |\n|---|---:|---:|---:|"]
    for k,name in (("all","Все"),("new","Новые источники"),("shared","Общие источники")):
        d=res[k]
        text[-1]+=f"\n| {name} | {d['questions']} / {d['clusters']} | {d['positive']} / {d['negative']} / {d['tie']} | {d['two_sided_cluster_sign_p']:.4f} |"
    text.extend(["На 27 вопросах с новыми источниками пять улучшений приходятся на четыре отдельные траектории. Этот масштаб ограничивает надёжность вывода по подгруппе. [Первичная парная оценка и интервалы](REPORT_RU.md) · [Расчёт](sparse-sign.json)"])
    (HERE/"SPARSE_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")
if __name__=="__main__":main()

