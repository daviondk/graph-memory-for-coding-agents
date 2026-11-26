"""Create this immutable three-seed checkpoint only when all three official pairs are available."""
from pathlib import Path
from shutil import copyfile
import hashlib,json,subprocess,sys
D=Path(__file__).resolve().parent;W=D.parents[1];BASE=W/"graph_memory_round34/native_comparison";PREV=BASE.parent/"native_checkpoint"
SEEDS=[13,17,29];ARMS=["full_rgcn","wo_chunk_adjacency"]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(p.read_bytes())
def pc(a):return f"{100*a:.2f}".replace(".",",")
def pp(a):return ("+" if a>0 else "")+pc(a)
def ci(values):return "["+"; ".join(pc(v) for v in values)+"]"
def effect(z,typ="conditional_ci"):return pp(z["delta"])+" "+ci(z[typ])
def main():
    if (D/"manifest.json").exists():
        subprocess.run([sys.executable,"-B",str(D/"check.py")],check=True);return
    assert sha(PREV/"manifest.json")=="80ab278122445e6d86303d2aae51d321b34b9649407603415dcb050691318ec9"
    if not (BASE/"report-3.md").exists():raise RuntimeError("Three paired official seeds have not yet been released")
    assert get(BASE/"interim-3.json")["seeds"]==SEEDS
    for f in ["PROTOCOL_RU.md","plan.json","compare.py","interim-3.json",*[f"{kind}-{seed}.{ext}" for seed in SEEDS for kind,ext in (("audit","json"),("seed","json"),("outcomes","json.gz"))]]:
        copyfile(BASE/f,D/f)
    for f in ["epoch-plan.json","dev-two-epochs.json"]:copyfile(PREV/f,D/f)
    tab=get(D/"interim-3.json");rows=["# ISETrace. Неизменяемый срез трёх полных парных сравнений","","На каждой из трёх инициализаций измерены три метода на тех же 2 000 вопросов и тех же 1 207 траекториях. Все шесть исходных показателей пересчитаны из фактических полных ранжирований с родной семантикой покрытия и строгого префикса. В срезе сохранены 6 000 сочетаний seed × вопрос с исходами каждого метода. В каждый файл входят ID вопроса и траектории, а также векторы R33, полного R-GCN и заново обученной абляции без chunk adjacency.","","| Seed | R33 FS@2048 | Полный R-GCN | Разница в п.п. [95% ДИ] | Без chunk adjacency | Разница в п.п. [95% ДИ] |","|---:|---:|---:|---:|---:|---:|"]
    for s in SEEDS:
        data=get(D/f"seed-{s}.json")
        # Compute each seed's means from its self-contained matched outcomes. Intervals are reported by the paired producer.
        import gzip
        per=json.loads(gzip.decompress((D/f"outcomes-{s}.json.gz").read_bytes()))
        means=[sum(row[j][0] for row in per.values())/2000 for j in (1,2,3)]
        for k in ("means","comparisons"):assert k in data
        cells=[str(s),pc(means[0]),pc(means[1]),effect(data["comparisons"][ARMS[0]]["full_support_2048"]),pc(means[2]),effect(data["comparisons"][ARMS[1]]["full_support_2048"])]
        rows.append("| "+" | ".join(cells)+" |")
    vals=tab["means"];comp=tab["comparisons"]
    rows+=["| Среднее | "+" | ".join([pc(vals["candidate"]["full_support_2048"]),pc(vals[ARMS[0]]["full_support_2048"]),effect(comp[ARMS[0]]["full_support_2048"]),pc(vals[ARMS[1]]["full_support_2048"]),effect(comp[ARMS[1]]["full_support_2048"])])+" |","",
        "Основные интервалы получены 10 000 парными перевыборками траекторий. Дополнительное одновременное ресемплирование seed даёт "+ci(comp[ARMS[0]]["full_support_2048"]["crossed_ci"])+" п.п. против полного и "+ci(comp[ARMS[1]]["full_support_2048"]["crossed_ci"])+" п.п. против абляции. Нижние и верхние пределы относятся к текущим трём инициализациям. При фиксации протокола пяти инициализаций общие тестовые задачи и результат первого seed были известны. Для основного решения предусмотрены ещё seed 37 и 41.","",
        "| Вторичная метрика, разница в п.п. | R33 минус полный граф [95% ДИ] | R33 минус абляция [95% ДИ] |","|---|---:|---:|"]
    for k in ["coverage_512","coverage_1024","coverage_2048","recall_5","mrr"]:
        rows.append("| "+k+" | "+effect(comp[ARMS[0]][k])+" | "+effect(comp[ARMS[1]][k])+" |")
    rows+=["","Эти отдельно рассчитанные вторичные интервалы описательные и не учитывают множественность. Делаем различие между попаданием фрагментов в бюджет контекста и рангом первого релевантного фрагмента.","","## Условия отбора и проверка","","Для каждого seed три модели используют общие Dense-веса, эвиденциальные единицы, токенизацию и spans. У R33 политика фиксируется по FS@2048, затем Coverage@2048 на dev580. Штатные R-GCN выбирают эпоху по node Recall@5 тех же 580 запросов. Отдельно зафиксирован повтор выбора всех десяти графовых эпох по той же бюджетной паре критериев, который начинается после основной очереди. Правило финальной проверки требует положительной нижней границы парного эффекта R33 по FS@2048 против обеих баз на пяти seed.","","Полные прогнозы закреплены в audit- и seed-файлах. Для отдельного пересчёта шести средних, парных эффектов и обоих типов интервалов из индивидуальных исходов выполнить `python -B check.py` с NumPy. Код для воспроизведения самих исходов из полных порядков сохранён в compare.py; снимок не является рабочей папкой наблюдения. [Числовые результаты](interim-3.json) · [Протокол](PROTOCOL_RU.md) · [Ранее закреплённые два seed](../../graph_memory_round34/native_checkpoint/REPORT_RU.md) · [Проверка выбора эпох](../../graph_memory_round34/dev_metric/PROTOCOL_RU.md)"]
    (D/"REPORT_RU.md").write_text("\n".join(rows)+"\n",encoding="utf8",newline="\n")
    subprocess.run([sys.executable,"-B",str(D/"check.py"),"--seal"],check=True)
if __name__=="__main__":main()
