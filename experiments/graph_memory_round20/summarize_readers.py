"""Write result tables from the sealed per-query evaluations."""
from pathlib import Path
import json
D=Path(__file__).resolve().parent
def get(p):return json.loads(p.read_bytes())
def fmt(n,dec=2):return f"{n:.{dec}f}".replace(".",",")
def diff(p):
    return f"{fmt(100*p['estimate'])} [{fmt(100*p['cluster_ci95'][0])}; {fmt(100*p['cluster_ci95'][1])}]"
methods={"prefix":"Префикс целых PU","skip":"Целые PU, добор по рангу","ratio":"Два PU, затем p/c","prob":"Два PU, затем p","unprotected":"Только блоки по p/c","nog":"p/c без двух структурных признаков","parent":"Ранг родителя","rrf":"Объединение рангов родителя и BM25"}
names={"dev":"Dense-FT, 500 dev","dense":"Dense-FT, 2 000 test","rgcn_availability":"R-GCN на подвыборке по доступности, 2 000 test","rgcn_hash64":"R-GCN на 64 хеш-выбранных траекториях, 2 000 test","rgcn":"R-GCN на полном train, 2 000 test"}
def table(path):
    res=get(path);stats=res["summary"];rows=["| Правило | Полный источник | FS, % | Coverage, % | Density, % | Среднее чтение, токенов |","|---|---:|---:|---:|---:|---:|"]
    for k,label in methods.items():
        v=stats[k];rows.append(f"| {label} | {v['hits']} / {res['n']} | {fmt(100*v['full_support'])} | {fmt(100*v['coverage'])} | {fmt(100*v['density'])} | {fmt(v['tokens'],1)} |")
    pairs=res["pairs"];rows.extend(["",f"Первичная пара p/c − skip, разность в п.п. и 95% парный ДИ по исходным траекториям. Full Support {diff(pairs['ratio-skip']['differences']['full_support'])}, Coverage {diff(pairs['ratio-skip']['differences']['coverage'])}. Поменяли исход {pairs['ratio-skip']['fs_wins']} выигрышей и {pairs['ratio-skip']['fs_losses']} потерь. [Все парные сравнения]({path.name}) · [Исходы по вопросам]({path.name.replace('results.json','outcomes.json.gz')})"])
    return "\n".join(rows)
def write(name,title,intro):
    root=D/name;parts=[f"# {title}",intro]
    for k,label in names.items():
        p=root/(k+"-results.json")
        if p.exists():parts.extend([f"## {label}",table(p)])
        strict=root/(k+"-render-results.json")
        if strict.exists():
            st=get(strict)["summary"];counts=", ".join(f"{m} {st[m]['render_overflows']}" for m in ("skip","ratio","prob","unprotected"))
            parts.append(f"Фактическую выдачу собрали из исходных цитат, разделённых переводом строки, повторно токенизировали и при необходимости укоротили до 2 048. Число выдач, потребовавших укорочения: {counts}. Полный эталон после этой операции потерян в {st['ratio']['lost_full']} выдачах p/c и {st['skip']['lost_full']} выдачах skip. [Строгая проверка и страты]({strict.name})")
    if name=="fine_read":
        st=get(root/"runtime-summary.json")["quantiles"];parts.append("## Стоимость чтения")
        parts.append(f"На фиксированной по хешу выборке из 128 траекторий при уже вычисленных рангах Dense-FT медиана выбора целых узлов — {fmt(st['skip']['median_ms'],4)} мс на вопрос, мелких блоков — {fmt(st['ratio']['median_ms'],3)} мс. Однократная подготовка геометрии фрагментов и BM25 заняла {fmt(st['full_index_build']['median_ms'],2)} мс на траекторию. Это CPU-измерение после получения рангов с пятью повторениями. Загрузка диска и нейросетевое кодирование предшествуют таймеру. [Квантили и условия](runtime-summary.json)")
    parts.append("[Протокол](PROTOCOL_RU.md) · [Веса](model.json)" if name in ("fine_read","fine_train","fine_lextrain") else "[Веса](model.json) · [Протокол](../PROTOCOL_RU.md)")
    (root/"REPORT_RU.md").write_text("\n\n".join(parts)+"\n",encoding="utf8")
if __name__=="__main__":
    write("fine_read","Чтение блоков внутри графовых узлов","Как расходовать 2 048 токенов, когда ранжировщик нашёл правильную область, но один узел содержит до 504 токенов? Весь опыт остаётся доступным. Завершённые события разбиваются на неперекрывающиеся блоки примерно по 64 WordPiece. Обучаем на 500 dev-вопросах скор пересечения мелкого блока с эталоном. В запросе доступны текущий текст, ранги родителя и BM25, геометрия и противоположная сторона вызова. Для p/c два самых высокоранговых узла защищены, далее используются новые координаты без перекрытия с ними. Публичный test уже применялся в предшествующих сериях. Обучение читателя использует разметку dev дополнительно к обучению самого Dense-FT. Ниже приведены восемь правил, первичная пара фиксирована заранее.")
    write("fine_lextrain","Можно ли обучить читателя без плотного поиска на train","На полном авторском train (3 894 вопроса, 2 410 траекторий) ранжируем целые фрагменты нативным BM25 и обучаем мелкозернистый читатель на тех же размеченных координатах. На других траекториях меняется способ получения родительского ранга. Коэффициенты и правила комплектации фиксированы. Это отдельная недорогая проверка переноса между ранжировщиками. Обучение использовало 2 224 062 пары «вопрос — блок», среди них 7 973 положительных. В режиме p/c микроблоки с малой ценой могут вытеснить более дорогие части составного свидетельства, поэтому дополнительно показан скор p.")
    for k in ("availability","hash64"):
        name="fine_subset/"+k;w=D/name/"model.json"
        if w.exists():
            m=get(w)
            write(name,"Чтение на совпадающей малой обучающей выборке",f"Веса читателя оценены по точным родительским рангам исходного Dense-FT на {m['questions']} train-вопросах из {m['trajectories']} траекторий. Графовая модель этого размера использует те же траектории. Новые ранги графа можно передать готовой линейной модели без изменения весов. Выбор состава, подвыборки и основная пара указаны в общем протоколе.")
    if (D/"fine_train/model.json").exists():
        write("fine_train","Мелкозернистый читатель на полном исходном train","Родительские ранги получены от полного исходного Dense-FT. Тонкий читатель использует все 3 894 тренировочных вопроса и исходные символьные интервалы.")

