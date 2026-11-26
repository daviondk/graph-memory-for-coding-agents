"""Calculate post-seal effects and issue a portable report and checksums."""
import gzip,hashlib,json
from itertools import combinations
from pathlib import Path
import numpy as np
from replicate import HERE,read,put,sha

def verify():
    plan=read(HERE/"plan.json");seal=read(HERE/"forecast-seal.json");rep=read(HERE/"results.json")
    assert len(plan["panel"])==len(set(plan["panel"]))==64 and not set(plan["panel"])&set(plan["old"])
    assert sha(HERE/"forecasts.json.gz")==seal["forecasts"] and sha(HERE/"outcomes.json.gz")==rep["outcomes"]
    raw=json.loads(gzip.decompress((HERE/"forecasts.json.gz").read_bytes()))
    outcomes=json.loads(gzip.decompress((HERE/"outcomes.json.gz").read_bytes()))
    errors=0;gains=[];saved=[];masks=0
    for q in plan["panel"]:
        row=raw[q];out=outcomes[q];edges=[set(r[:2]) for r in row["rows"]];order=row["order"]
        first_four=set(order[:4]);idx=[j for j,e in enumerate(edges) if first_four&e]
        cut=idx[:len(row["winners"])];ws=[set(p) for p in row["winners"]]
        roots_prefix=set(order[:4]);star=set()
        for r in roots_prefix:star.update([j for j,e in enumerate(edges) if r in e][:3])
        wrong=0
        for removed,ref,arms in out["scenarios"]:
            R=set(removed);head=set(i for i in order if i not in R)
            G=set([d for d in order if d in head][:2])
            oracle=next(i for i,e in enumerate(edges) if not e&R and e&G)
            actual=[i for i in cut if not edges[i]&R and edges[i]&G]
            assert oracle==ref==arms["star_union"]==arms["lazy"] and oracle in star and edges[oracle] in ws
            if len(R)==2 and (not actual or actual[0]!=oracle):wrong+=1
            masks+=1
        assert row["encoder_calls"]==55==len(row["calls"]) and len(set(tuple(x[1]) for x in row["calls"] if x[0]=="lazy"))==30
        gains.append(wrong/45*100);saved.append(len(star)-len(ws));errors+=wrong
    assert masks==3584 and errors==64*45-rep["k_correct"]["2"]["pool4_matched"]
    draws=np.random.default_rng(31463).integers(64,size=(10000,64))
    assert np.allclose(np.quantile(np.array(gains)[draws].mean(1),[.025,.975]),rep["paired"]["pool4_matched"]["ci_pp"])
    assert np.allclose(np.quantile(np.array(saved)[draws].mean(1),[.025,.975]),rep["star_minus_lazy_saved"]["ci_rows"])
    if (HERE/"manifest.json").exists():
        inventory=read(HERE/"manifest.json")
        assert set(inventory)=={f.name for f in HERE.iterdir() if f.is_file() and f.name!="manifest.json"}
        assert all(sha(HERE/k)==v for k,v in inventory.items())
    return masks

def report():
    r=read(HERE/"results.json");p=r["paired"]["pool4_matched"];star=r["star_minus_lazy_saved"];mem=r["mean_memory_rows"];c=r["k_correct"]["2"]
    interval=lambda v:"["+", ".join(f"{a:.2f}" for a in v)+"]"
    lines=["# Репликация на 64 новых вопросах HotpotQA","",
           f"На 64 заранее выбранных вопросах из HotpotQA dev измеряли воспроизведение решения Beam Retrieval с шириной 2 после удаления двух источников. Вопросы имеют по 10 предложенных документов и не пересекаются с первыми восемью. Полный динамический подбор определяет эталонный результат каждого из 45 сочетаний удалений на вопрос. Графовое дерево воспроизвело {c['lazy']}/2880 результатов. Префикс с таким же числом строк среди 30 возможных пар четырёх корней воспроизвёл {c['pool4_matched']}/2880. Парное изменение {p['delta_pp']:.2f} п.п., 95% ДИ {interval(p['ci_pp'])}, {p['wins']} вопросов с выигрышем, {p['ties']} с равным результатом. Единица перевыборки — вопрос. [Метод Beam Retrieval](https://aclanthology.org/2024.naacl-long.96/)","",
           "| Метод | Точных ответов при двух отзывах | Сохранено пар на вопрос, среднее |","|---|---:|---:|"]
    for m,title in [("initial","Старые 17 пар с перерасчётом корней"),("global_matched","Общий префикс"),("pool4_matched","Префикс доступных четырём корням пар"),("static","Дерево статического ранжирования"),("star_union","Объединение трёх лучших соседей каждого из четырёх корней"),("lazy","Дерево достижимых победителей"),("pool4","Все пары четырёх корней"),("full","Все пары")]:
        lines.append(f"| {title} | {c[m]}/2880 | {mem[m]:.2f} |")
    lines+=["",f"Точный дополнительный контроль по соседям при тех же четырёх адресах сохраняет в среднем на {star['mean_rows']:.2f} пары больше дерева, 95% ДИ {interval(star['ci_rows'])}. Полный динамический лучший адрес и общий негейтированный победитель разошлись в {r['order_changed']}/2880 случаях. Совпадение исходно выбранной пары с двумя эталонными документами составило {r['gold_initial_hits']}/64 без отзывов. Извлечение абзацев и генерация ответа в данный опыт не входят.","",
           f"На каждом из 64 вопросов при построении реально вычислены 10 баллов документов и ровно 30 баллов уникальных пар по требованию. Без повторного использования порядок обхода запрашивает в среднем {r['mean_without_memo']:.2f} оценок пар. Контроль из 30 рёбер также требует ровно 30 обращений к модели. Для полного референса отдельно рассчитаны ещё 15 пар. Медиана затрат на каждой фазе составила {r['median_phase_s']['hop1']:.2f} с, {r['median_phase_s']['lazy']:.2f} с и {r['median_phase_s']['full_remainder']:.2f} с соответственно. Загрузка других процессов меняется. Первичную стоимость ограничивает число потенциально допустимых пар, экономия слотов достигается при последующем хранении. [Доказательство](COST_BOUND_RU.md)","",
           "Все 448 результатов при повторном прогоне восьми исходных контрольных вопросов сверены с авторской реализацией ранее вычисленного полного порядка. Основной корпус для репликации ограничен вопросами с десятью кандидатами и является частью знакомого публичного dev. Распределение реальных отказов у кодовых агентов требует собственного наблюдения. [Первичный протокол](PROTOCOL_RU.md) · [Дополнительный контроль](STAR_CONTROL_RU.md) · [Результаты](results.json)"]
    (HERE/"REPORT_RU.md").write_text("\n".join(lines)+"\n",encoding="utf8")

if __name__=="__main__":
    import sys
    if "--verify" in sys.argv:
        print("Verified states",verify())
    else:
        from score_replication import main
        main();print("Verified states",verify());report()
        put(HERE/"manifest.json",{f.name:sha(f) for f in HERE.iterdir() if f.is_file() and f.name!="manifest.json"})
        print("Verified states after signing",verify(),sha(HERE/"manifest.json"))

