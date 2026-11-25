"""Sensitivity to duplicate gold-bearing fields and number of source events. Frozen methods."""
from pathlib import Path
import sys

from validate_transfer import HERE, TYPED, FACTOR, ROUND, read, write, digest, paired, interval

R19 = ROUND.parent / "graph_memory_round19"
R18 = ROUND.parent / "graph_memory_round18"


def rows(stage):
    if stage == "extra80":
        all_rows = read(TYPED / "outcomes.json.gz")
        typ = {r["q"]: r for r in all_rows if r["arm"] == "train/role_degrees" and r["policy"] == "prefix"}
        dense = {r["q"]: r for r in all_rows if r["arm"] == "dense" and r["policy"] == "prefix"}
        ffile = FACTOR / "hash64-extra-outcomes.json.gz"
        gold = read(R19 / "write_transfer/gold-spans.json.gz")
        src = [TYPED / "outcomes.json.gz"]
    else:
        typed_src = TYPED.parent / "mechanism/test-train/outcomes.json.gz"
        dense_src = TYPED.parent / "outcomes.json.gz"
        typ = {r["q"]: r for r in read(typed_src) if r["arm"] == "role_degrees" and r["policy"] == "prefix"}
        dense = {r["q"]: r for r in read(dense_src) if r["arm"] == "dense" and r["policy"] == "prefix"}
        ffile = FACTOR / "hash64-outcomes.json.gz"
        gold = read(R18 / "isetrace_official/gold-spans.json.gz")
        src = [typed_src, dense_src]
    cells = {"role_degrees": typ}
    if ffile.exists():
        obj = read(ffile)
        cells["factor"] = obj["prefix/factor"]
        src.append(ffile)
    assert all(set(v) == set(dense) for v in cells.values())
    return cells, dense, gold, src


def calc(stage):
    cells, dense, gold, files = rows(stage)
    path = R19 / "split_overlap/overlap-flags.json.gz"
    flags = {r["q"]:r for r in read(path) if r["train"] == "dense" and r["q"] in dense}
    assert set(flags) == set(dense)
    groups = {"all": set(dense), "single_event": set(), "multi_event": set(), "no_exact_field_match": set(), "exact_field_match": set()}
    for q in sorted(dense):
        assert gold[q] and dense[q]["t"] == flags[q]["t"]
        groups["exact_field_match" if flags[q]["gold_field"] else "no_exact_field_match"].add(q)
        groups["multi_event" if len({r["event_id"] for r in gold[q]}) > 1 else "single_event"].add(q)
    vals = {}
    for g, qs in groups.items():
        if qs:
            vals[g] = {n:paired(data,dense,qs) for n,data in cells.items()}
    out = {"sha256":{str(f.relative_to(ROUND.parent)): digest(f) for f in [*files, path, HERE / "STRATA_PROTOCOL_RU.md"]},
           "estimates": vals, "denominators":{g:len(v) for g,v in groups.items()}}
    write(HERE / (stage+"-strata.json"),out)
    return out


def report():
    parts = ["# Дословное совпадение обучающего материала и число исходных событий",
             "На одном вопросе обе политики получают идентичный Dense-FT, одни родительские PU и одинаковое правило префикса при 2 048 токенах. «Поле совпало» означает полное дословное равенство хотя бы одного содержащего эталон поля вопроса и одного из полей обучения. Разметка выбирает только аналитическую подгруппу после завершения ранжирования. Указанная в таблице неопределённость учитывает зависимость вопросов одной траектории. Для вопросов с редкими совпадениями сравнение описательное."]
    names={"all":"Все","single_event":"Одно событие","multi_event":"Несколько событий","no_exact_field_match":"Без совпадения поля","exact_field_match":"Совпало поле"}
    for stage,title in (("test","Основной test, повторный анализ"),("extra80","Дополнительные вопросы, заранее заданное разделение")):
        path = HERE / (stage+"-strata.json")
        if not path.exists():
            continue
        data = read(path)
        tab = ["| Подгруппа | Вариант | Вопросы / траектории | Успехи метод / Dense | Выигрыши / потери | Δ FS, п.п. [95% ДИ] | Δ Coverage, п.п. [95% ДИ] |","|---|---|---:|---:|---:|---:|---:|"]
        for g, label in names.items():
            for arm, c in data["estimates"].get(g, {}).items():
                armname = "Факторизованный prior" if arm=="factor" else "Роль и степени"
                tab.append(f"| {label} | {armname} | {c['n']} / {c['trajectories']} | {c['hits']} / {c['base_hits']} | {c['wins']} / {c['losses']} | {interval(c,'full_support')} | {interval(c,'coverage')} |")
        parts.extend(["## "+title, "\n".join(tab), f"[Машиночитаемые оценки]({path.name})"])
    parts.append("[Протокол](STRATA_PROTOCOL_RU.md) · [Проверка по общим траекториям](REPORT_RU.md)")
    (HERE/"STRATA_RU.md").write_text("\n\n".join(parts)+"\n",encoding="utf8")

if __name__=="__main__":
    for stage in sys.argv[1:]:
        assert stage in ("test","extra80")
        calc(stage)
    report()

