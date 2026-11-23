"""Write the reproducible numerical report after sealed forecasts and independent checks finish."""
from pathlib import Path
import importlib.metadata
import json
import platform
import shutil
import sys
from discover import ROOT,BASE,load,pilot,write
from score import compare

def representation_effects():
    outcomes = load("outcomes.json.gz")
    earlier = set()
    for path in (BASE/"cohort.json", BASE/"replication/cohort.json"):
        earlier.update(json.loads(path.read_bytes())["selected"])
    assert len(earlier) == 128
    write("sensitivity-excluded-ids.json", sorted({r["q"] for r in outcomes if r["t"] in earlier}))
    effects = {}
    for label, observations in (("all", outcomes), ("no_previous_trajectories", [r for r in outcomes if r["t"] not in earlier])):
        def index(view, arm, mode=None):
            return {r["q"]: r for r in observations if r["view"] == view and r["arm"] == arm and (mode is None or r["memory_mode"] == mode)}
        cross = {arm: compare(index("provenance", arm), index("flat", arm)) for arm in ("prefix", "clip", "skip", "value")}
        modes = {}
        for mode in sorted({r["memory_mode"] for r in observations}):
            pair, cost = index("provenance","related",mode), index("provenance","value",mode)
            modes[mode] = {"queries":len(pair), "related":int(sum(r["full_support"] for r in pair.values())),
                           "value":int(sum(r["full_support"] for r in cost.values())), "paired":compare(pair,cost)}
        effects[label] = {"provenance_minus_flat":cross, "exploratory_related_minus_value_by_mode":modes}
    write("representation.json", effects)
    return effects

def interpret_placebo(notes):
    data=load("placebo-results.json")
    notes.extend(["","## Контроль с переставленными связями","",
                  "После анализа основных исходов зафиксированы две нулевые модели и 16 seed. Правило упаковки и исходные ранги сохранены. На каждом seed менялось соответствие между вызовами и выходами одной операции внутри одной траектории. Строгая перестановка сохраняла также число аргументных и выходных чанков у каждого вызова. Вторая сохраняла число событий каждой стороны. Интервал отражает разброс по траекториям для разности настоящей политики и средней по 16 перестановкам. Выбор нулевой модели ограничивает интерпретацию эффекта. [Замороженный post-hoc протокол](PLACEBO_PROTOCOL_RU.md) · [Метрики и все seed](placebo-results.json) · [SHA-256 прогнозов перед оценкой](placebo-forecast-lock.json)",
                  "", "| Выборка и сохраняемая степень | Настоящие связи, % | Переставленные, % | Δ [95% ДИ], п.п. | Токены, настоящие / переставленные | Переставлено пар |",
                  "|---|---:|---:|---:|---:|---:|"])
    for label in ("all","no_previous_trajectories"):
        for mode,descr in (("strict","чанки и события"),("event_degree","события")):
            c=data[label][mode]
            a,b=c["trajectory_bootstrap_ci95"];effect=c["real_minus_mean_placebo"]
            notes.append((f"| {c['n']}, {descr} | {100*c['real']['full_support']:.2f} | {100*c['placebo']['full_support']:.2f} | "
                          f"{100*effect:+.2f} [{100*a:+.2f} … {100*b:+.2f}] | {c['real']['tokens']:.2f} / {c['placebo']['tokens']:.2f} | "
                          f"{c['rewired_calls']}/{c['all_two_sided_calls']} |").replace(".",","))
    st=data["all"]["strict"];overlap=data["overlap"]
    notes.extend(["",f"На строгом контроле состав прочитанных узлов изменился в {100*st['mean_changed_fraction']:.2f}% комбинаций запрос–seed. Истинное соответствие повышает полноту сверх эффекта гранулярности, степени и расхода в этой постановке. В исходном исследовании было назначено {overlap['r17_assigned_queries']} запросов; ранее прошли сопоставление {overlap['r17_scored_queries']}. Полное сопоставление восстановило ещё {overlap['official_on_r17_trajectory_absent_r17_scored']} на ранее назначенных траекториях. Исключение этих траекторий целиком даёт 2 000 − 205 = 1 795 запросов."])

def count(m,key):
    return m[key]["full_count"]
def ci(pair):
    a,b=pair["trajectory_bootstrap_ci95"]
    return f"{100*pair['delta']:+.2f} п.п. [{100*a:+.2f}; {100*b:+.2f}]".replace(".",",").replace("п,п,","п.п.").replace("; "," … ")
def generate():
    results=load("results.json"); split=load("split-verification.json")
    current=results["all"];new=results["no_previous_trajectories"];cal=results["official_calibration"]
    m=current["metrics"];p=current["paired"]
    rows=load("cohort.json")
    effects=representation_effects()
    notes=["# Полный тест ISETrace. Что происходит при переполнении бюджета памяти",""]
    notes.append(f"Обработаны все восемь исходных шардов. Опубликованная калибровка flat BM25 — 759/2 000 запросов с полным комплектом свидетельств при бюджете 2 048. Пересчёт штатным кодом дал **{cal['observed_count']}/{cal['observed_n']}**. Совпадение проверенной численной сигнатуры исследования: **{'да' if cal['matches'] and cal['shape_match'] else 'нет'}**. [Состав выборки](split-verification.json) · [Авторы, таблица 1](https://arxiv.org/html/2609.25913v3)")
    notes.extend(["","| Представление и политика | Полная поддержка | Full Support, % | Coverage, % | Density, % | Средний расход E5-токенов |",
                  "|---|---:|---:|---:|---:|---:|"])
    desc={"prefix":"штатный префикс","skip":"добор целыми узлами без изменения порядка","value":"добор по баллу / √стоимости","clip":"часть следующего узла до лимита","related":"приоритет пары одного вызова"}
    for v,vtitle in (("flat","Плоские окна"),("provenance","Аргументы и результаты")):
        for h in ("prefix","clip","skip","value","related"):
            if f"{v}/{h}" not in m:continue
            a=m[f"{v}/{h}"]
            notes.append(f"| {vtitle}, {desc[h]} | {a['full_count']}/{a['n']} | {100*a['full_support']:.2f} | {100*a['coverage']:.2f} | {100*a['density']:.2f} | {a['tokens']:.1f} |".replace(".",","))
    notes.extend(["",f"Пусть P — штатный непрерывный префикс ранжирования. Правила skip и value добавляют к P целые фрагменты, которые ещё помещаются. Покрытие эталона и Full Support тогда не могут уменьшиться относительно P. Нетривиальны размер эффекта и его зависимость от реально использованного числа токенов. Усечение clip отдаёт остаток следующему фрагменту и служит сильным контролем расхода. Все сравнения ниже парные. Интервалы — описательная 95% кластерная оценка по траекториям, 10 000 повторений.","",
                  "| Сравнение Full Support | Выигрыши | Потери | Разница [95% ДИ] |","|---|---:|---:|---:|"])
    for v in ("flat","provenance"):
        for h in ("skip-prefix","skip-clip","value-skip","value-clip")+(("related-skip","related-value") if v=="provenance" else ()):
            a=p[v+"/"+h]
            notes.append(f"| {v}, {h} | {a['full_wins']} | {a['full_losses']} | {ci(a)} |")
    cross = effects["all"]["provenance_minus_flat"]["prefix"]
    notes.extend(["",f"При исходном префиксе переход с плоских окон на аргументы и результаты дал {ci(cross)} Full Support. Число запросов с улучшением — {cross['full_wins']}, с ухудшением — {cross['full_losses']}. Этот контраст одновременно отражает границы фрагментов и набор полей, доступных ранжировщику. [Парные сравнения при четырёх одинаковых политиках](representation.json)",
                  "", "**Разведочный разрез по типу запроса.** У обоих методов остаётся тот же префикс. В остатке related поднимает фрагменты с тем же идентификатором вызова и противоположной ролью, затем следует исходному порядку BM25. Value сортирует остаток по BM25 / √токенов. Ни один метод не использует тип вопроса или эталон при выдаче.",
                  "", "| Тип | Запросов | Приоритет пары | Нормировка стоимости | Выигрыши / потери |", "|---|---:|---:|---:|---:|"])
    for mode, row in effects["all"]["exploratory_related_minus_value_by_mode"].items():
        cmp=row["paired"]
        notes.append(f"| {mode} | {row['queries']} | {row['related']} | {row['value']} | {cmp['full_wins']} / {cmp['full_losses']} |")
    interpret_placebo(notes)
    notes.extend(["","**Перенос за пределы прежних экспериментальных задач.** При исключении всех ранее назначенных 128 ID из разведочной серии осталось "
                  f"{new['metrics']['provenance/prefix']['n']} запросов и {new['unique_trajectories']} траекторий. На этом заранее заданном срезе для provenance префикс дал {count(new['metrics'],'provenance/prefix')}, пропуск — {count(new['metrics'],'provenance/skip')}, усечение — {count(new['metrics'],'provenance/clip')}, нормировка по стоимости — {count(new['metrics'],'provenance/value')}, приоритет пары — {count(new['metrics'],'provenance/related')} полных комплектов. [Все парные сравнения и расходы](results.json)","",
                  f"**Проверки исходных данных.** Из {split['native_match']['trajectories_seen']} сырых траекторий авторский канонический адаптер принял {split['native_match']['trajectories_accepted']}. Из 6 597 v7-запросов разрешены {split['resolved']}. В тесте {split['groups']['test']['trajectories']} траекторий и {len(rows)} запросов, в том числе {split['modes'].get('direct_recall',0)} direct, {split['modes'].get('linked_recall',0)} linked и {split['modes'].get('multi_fact_recall',0)} multi-fact. Для всех запросов сохранены координаты эталонных символов и ранги, а SHA-256 прогнозов фиксируется до оценивания. Официальный алгоритм задаёт тест по первым уникальным валидным траекториям после полного сопоставления. Отдельный опубликованный список ID для побайтного сопоставления не найден. [Идентификаторы теста](cohort.json) · [Пины данных](source-lock.json) · [Проверенные прогнозы](forecast-lock.json)","",
                  "**Границы результата.** Полнота поддержки означает покрытие всех эталонных символов в правильных исходных полях. Окончательный ответ модели и успех решения исходной задачи здесь не измерялись. В авторской статье Residual R-GCN получила 77,33 ± 0,53% Full Support@2048 по пяти seed на полном тесте. Эта работа воспроизводит детерминированный baseline BM25, изучает способ упаковки на тех же исходных координатах и не переобучает графовую модель. Варианты на provenance и flat также различаются гранулярностью и составом допустимых полей. [Авторское сравнение R-GCN с точным Dense-FT seed](https://arxiv.org/html/2609.25913v3) · [Проверка и воспроизведение](REPRODUCE_RU.md)",""])
    (ROOT/"REPORT_RU.md").write_text("\n".join(notes),encoding="utf8",newline="\n")
    env={"python":sys.version.split()[0],"platform":platform.platform(),"packages":{n:importlib.metadata.version(n) for n in ("numpy","pydantic","rank-bm25","tokenizers","requests")}}
    write("environment.json",env)
    source=pilot.CACHE.parent
    logs=ROOT/"logs";logs.mkdir(exist_ok=True)
    for log in ["full-fetch.log","full-fetch.err","official-discover.log","official-discover.err","official-rank.log","official-rank.err",*[f"rank-full-{i}.{ext}" for i in range(8) for ext in ("log","err")]]:
        if (source/log).exists():shutil.copyfile(source/log,logs/log)
    files=sorted(f for f in ROOT.rglob("*") if f.is_file() and f.name!="MANIFEST_SHA256.json" and "__pycache__" not in f.parts)
    assert all(f.stat().st_size<64*1024**2 for f in files)
    manifest={f.relative_to(ROOT).as_posix():pilot.sha(f) for f in files}
    write("MANIFEST_SHA256.json",manifest)
    print(len(manifest),"files",sum(f.stat().st_size for f in files),"bytes",pilot.sha(ROOT/"MANIFEST_SHA256.json"))
if __name__=="__main__":generate()
