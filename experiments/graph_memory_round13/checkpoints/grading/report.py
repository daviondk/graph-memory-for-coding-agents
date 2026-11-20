"""Independently validate selected checkpoints and present paired results including missing tests."""
from pathlib import Path
import gzip,hashlib,json
ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    s=load(ROOT/"results.json");sel=load(ROOT.parent/"selection.json")
    assert s["complete"] and len(s["rows"])==len(sel)
    parts=["# Оценка последних снимков", 
           "",f"Оценено {s['n']} выбранных эпизодов. В официальной подаче решено {s['solver_resolved']}, при проверке последнего доступного снимка — {s['checkpoint_resolved']}. Число отсутствующих наблюдений — {s['unavailable']}.",
           "","| Задача и условие | Поздний вход | Размер снимка, Б | SHA совпал с подачей | Состояние оценщика | F2P | Потери P2P |",
           "|---|---|---:|---|---|---:|---:|"]
    for r in s["rows"]:
        iid,m,_=r["episode"].split("|");res=ROOT/iid/m/"result.json"
        assert load(res)==r
        last=sel[r["episode"]]["last"]
        if last:
            b=gzip.decompress((ROOT.parent/"patches"/(r["selected_sha"]+".patch.gz")).read_bytes())
            assert sha(b)==last["sha"] and len(b)==last["size"]
        if r.get("raw_outputs"):
            for name,d in r["raw_outputs"].items():assert sha((res.parent/name).read_bytes())==d
        stages={"resolved":"решено","unresolved":"не решено","no_patch":"пустой патч","no_observation":"нет наблюдения","harness_error":"ошибка оценщика"}
        text=lambda v:"—" if v is None else str(v)
        parts.append(f"| [{iid}, {m}]({iid}/{m}/result.json) | {'да' if r['left_truncated'] else 'нет'} | {text(r.get('selected_bytes'))} | {'да' if r.get('reused') else 'нет'} | {stages[r['status']]} | {text(r.get('f2p'))} | {text(r.get('lost_p2p'))} |")
    parts+=["","Все строки выбраны до доступа к результату эталонной проверки. При полном совпадении SHA ровно для того же эпизода дополнительно сравнены сырые байты со входом официального оценщика. Если они совпали, использовалась та же квитанция и сохранены нативные логи. Во всех остальных случаях оригинальные проверяющие скрипты запускались заново в отдельном каталоге, контейнере без сети с 0,5 CPU. При пустом патче проверка завершается до запуска тестов. Данные этой таблицы характеризуют отдельную диагностическую серию. [Условия основного опыта](../PROTOCOL_RU.md) · [Опечатанный отбор](../sealed.json) · [Квитанции](results.json)"]
    (ROOT/"REPORT_RU.md").write_text("\n".join(parts)+"\n",encoding="utf8")
if __name__=="__main__":main()
