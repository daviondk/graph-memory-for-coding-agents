"""Read complete feedback-only frozen traces after the original scorer has published the result."""
import gzip
import json
import statistics
from pathlib import Path

def write(w,read,table,fmt):
    home=Path(__file__).resolve().parents[1]/"alfworld/text_only"
    marks=[s for s in ["results.json","summary.json","scores.json"] if (home/s).is_file()]
    if not marks:
        raise FileNotFoundError("Waiting for original feedback-only scorer")
    scores=json.loads((home/marks[0]).read_bytes())
    roster=read("alfworld/text_only/roster.json")["valid_unseen"]
    legs=["none","pose_cycle","cursor","full","trained"]
    data={};equal_actions=0
    for file in sorted((home/"eval").glob("*.json.gz")):
        record=json.loads(gzip.decompress(file.read_bytes()))
        ep=record["episode"]; arms={r["arm"]:r for r in record["records"]}
        assert set(arms)==set(legs)
        data[ep]={}
        for k,r in arms.items():
            steps=r["steps"]
            assert 0<len(steps)<=50
            success=bool(steps[-1][2])
            data[ep][k]=(success,len(steps) if success else 50,sum(not bool(e[4]) for e in steps),len(steps))
        same=[s[0] for s in arms["pose_cycle"]["steps"]]==[s[0] for s in arms["cursor"]["steps"]]
        equal_actions+=same
    assert set(data)=={g["episode"] for g in roster} and len(data)==134
    def val(k,l):return sum(d[k][l] for d in data.values())
    for k in legs:
        orig=scores["overall"]["arms"][k]
        assert orig["won"]==val(k,0) and orig["attempts"]==val(k,3)
        assert abs(orig["mean_capped_steps"]-val(k,1)/134)<1e-12
    assert equal_actions==scores["identical_to_pose_action_traces"]["cursor"]
    names=["Без истории осмотров","Цикл от текущей позиции","Явный курсор","Все осмотренные места","Все места и частоты находок на train"]
    table(["Правило поиска","Решено из 134","Шаги в среднем¹","Выполнено команд"],[
        [name,val(k,0),fmt(val(k,1)/134),val(k,3)] for k,name in zip(legs,names)],[8.0,2.9,3.0,3.2])
    w.p("¹ Каждый проигрыш учитывается как 50 шагов. Контроллер явно получал собственную последнюю команду и буквальный отклик. Числа в последнем столбце суммируют реальные выполненные команды, включая неуспешные попытки.")
    if equal_actions==134:
        message="Во всех 134 играх циклический обход от текущей позиции и курсор совпали по каждому действию. Для такого порядка обхода сохранение курсора ничего не добавило."
    else:
        message=f"Циклический обход от текущей позиции и явный курсор дали одинаковые последовательности команд в {equal_actions} из 134 игр. При сопоставлении полезно учитывать, что общая позиция и память исследования могут по-разному переживать смену фазы."
    w.p(message)
    for k,base,caption in [("full","pose_cycle","Полный список относительно бесплатного цикла"),("trained","full","Добавление обучающих частот к полному списку")]:
        wins=sum(d[k][0] and not d[base][0] for d in data.values())
        losses=sum(d[base][0] and not d[k][0] for d in data.values())
        delta=(val(k,1)-val(base,1))/134
        c=scores["contrasts"][k+"-"+base]
        assert (wins,losses)==(c["wins"],c["losses"])
        lo,hi=c["paired_floorplan_cluster95"]
        w.p(f"{caption} дало {wins} выигранных и {losses} потерянных игр. Изменение успеха {fmt(c['delta_pp'])} п.п., интервал по четырём планировкам [{fmt(lo)}; {fmt(hi)}]. Средняя разница составила {fmt(delta)} шага.")

