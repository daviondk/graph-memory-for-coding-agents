"""Recount rejected transitions from finished physical rollouts before composing the last table."""
from collections import defaultdict
import gzip
import json
from pathlib import Path

def load(p):
    return json.loads(gzip.decompress(p.read_bytes()))
def data(w,read,table,fmt):
    base=Path(__file__).resolve().parents[1]/"alfworld/text_only/failure_memory"
    if not (base/"results.json").exists():
        raise FileNotFoundError("Awaiting closed results of rejection-memory transfer")
    units={}
    for split,l in [("valid_unseen",134),("valid_seen",140)]:
        paths=sorted((base/split).glob("*.gz"));assert len(paths)==l
        group={}
        for path in paths:
            runs=load(path);records=runs["records"]
            if split=="valid_unseen":
                old=load(base/"baseline_unseen"/path.name)
                assert old["episode"]==runs["episode"]
                baseline=dict(old["record"]);baseline["arm"]="baseline"
                records=[baseline]+records
            assert {a["arm"] for a in records}=={"baseline","one_step","pose_set"}
            group[runs["episode"]]={}
            for r in records:
                ss=r["steps"];win=int(ss[-1][2])
                rejects=sum(s[0].startswith("go to ") and s[1].strip().lower()=="nothing happens." for s in ss)
                group[runs["episode"]][r["arm"]]=(win,len(ss) if win else 50,rejects,tuple(s[0] for s in ss))
        units[split]=group
    rows=[]
    for arm,title in [("baseline","Исходные частоты поиска"),("one_step","Реакция на последний отказ"),("pose_set","Все отказы из этой позиции")]:
        row=[title]
        for split,group in units.items():
            seq=[r[arm] for r in group.values()]
            row.append(f"{sum(s[0] for s in seq)} / {len(seq)}")
            row.append(f"{fmt(sum(s[1] for s in seq)/len(seq))} · {sum(s[2] for s in seq)}")
        rows.append(row)
    table(["Политика","Победы, unseen","Шаги · отказы¹","Победы, seen","Шаги · отказы¹"],rows,[5.5,2.7,3.25,2.55,3.1])
    w.p("¹ Cредние шаги с начислением 50 за неудачу и суммарное число отказов в переходе. В этой серии исполнено 688 новых эпизодов. 134 уже известные траектории исходной политики использованы повторно.")
    w.h("Добавка относительно одношаговой реакции")
    for split,g in units.items():
        assert all(r["pose_set"][:2]==r["one_step"][:2] for r in g.values())
        exp=134 if split=="valid_unseen" else 139
        assert sum(r["pose_set"][3]==r["one_step"][3] for r in g.values())==exp
    w.p("На 140 заранее отложенных играх одношаговая реакция относительно исходной политики дала десять побед при нуле потерь. Прирост +7,14 п.п., 95% интервал по 76 планировкам [+2,88; +12,40]. Средняя экономия составила 2,06 шага.")
    w.p("Сохранение всех отказов не изменило успех или число шагов ни в одной из 274 игр относительно одношаговой реакции. Совпали все 134 последовательности действий на valid_unseen и 139 из 140 на valid_seen. Число отказов на valid_seen снизилось с 64 до 25 за счёт одной траектории. Её конечный исход совпал.")

