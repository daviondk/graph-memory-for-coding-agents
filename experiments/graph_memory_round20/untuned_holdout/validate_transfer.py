"""Audit frozen records from three readers and report paired estimates on the same held-out rows."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
TYPED = ROUND / "typed_reader/holdout80"
FACTOR = ROUND / "factor_reader"
FIELDS = ("full_support", "coverage", "density", "f1", "tokens")


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def paired(rows, base, questions):
    trajectories = defaultdict(list)
    for q in sorted(questions):
        a, b = rows[q], base[q]
        assert a["t"] == b["t"]
        trajectories[a["t"]].append([a[f] - b[f] for f in FIELDS])
    keys = sorted(trajectories)
    part = np.asarray([np.sum(trajectories[t], axis=0) for t in keys])
    sizes = np.asarray([len(trajectories[t]) for t in keys])
    delta = part.sum(axis=0) / sizes.sum()
    samples = []
    rng = np.random.default_rng(13)
    for _ in range(40):
        picks = rng.integers(0, len(keys), size=(250, len(keys)))
        samples.extend(part[picks].sum(axis=1) / sizes[picks].sum(axis=1)[:, None])
    intervals = np.quantile(samples, [0.025, 0.975], axis=0)
    diffs = [rows[q]["full_support"] - base[q]["full_support"] for q in questions]
    return {
        "n": len(questions), "trajectories": len(keys),
        "hits": int(sum(rows[q]["full_support"] for q in questions)),
        "base_hits": int(sum(base[q]["full_support"] for q in questions)),
        "wins": sum(v > 0 for v in diffs), "losses": sum(v < 0 for v in diffs),
        "mean": {f: float(np.mean([rows[q][f] for q in questions])) for f in FIELDS},
        "effects": {f: [float(delta[k]), *intervals[:, k].tolist()] for k, f in enumerate(FIELDS)},
    }


def audit():
    plan = read(TYPED / "source-plan.json")
    queries = plan["queries"]
    extra = set(queries)
    tids = set(queries.values())
    novel = set(plan["novel_trajectories"])
    split = read(ROUND.parent / "graph_memory_round19/trained_rank/split.json.gz")
    assert not extra.intersection(r["q"] for r in split["dev"] + split["train"] + split["test"])
    assert not tids.intersection(r["t"] for r in split["train"] + split["test"])
    assert tids - {r["t"] for r in split["dev"]} == novel
    assert (len(extra), len(tids), len(novel)) == (80, 74, 21)
    groups = {
        "all": sorted(extra), "novel": sorted(q for q, t in queries.items() if t in novel),
        "shared": sorted(q for q, t in queries.items() if t not in novel),
    }
    ranks = HERE / "dense-ranks-extra80.json.gz"
    rank_hash = digest(ranks)
    assert read(HERE / "forecast-seal.json")["ranks"] == read(TYPED / "forecast-seal.json")["raw_sha"] == rank_hash
    assert read(HERE / "forecast-seal.json")["forecast"] == digest(HERE / "predictions.json.gz")
    assert read(TYPED / "forecast-seal.json")["predictions"] == digest(TYPED / "forecasts.json.gz")

    typed = defaultdict(dict)
    for r in read(TYPED / "outcomes.json.gz"):
        key = r["arm"] + "/" + r["policy"]
        assert r["q"] not in typed[key]
        typed[key][r["q"]] = r
    micro = read(HERE / "outcomes.json.gz")
    factor = {}
    files = [HERE / "outcomes.json.gz", TYPED / "outcomes.json.gz"]
    for cohort in ("hash64", "availability"):
        out = FACTOR / (cohort + "-extra-outcomes.json.gz")
        if out.exists():
            files.append(out)
            seal = read(FACTOR / (cohort + "-extra-seal.json"))
            assert seal["upstream"] == rank_hash
            assert seal["file"] == digest(FACTOR / (cohort + "-extra-ranks.json.gz"))
            factor[cohort] = read(out)
    for study in [typed, micro, *factor.values()]:
        for rows in study.values():
            assert set(rows) == extra
            for q, r in rows.items():
                assert r["t"] == queries[q]
                assert 0 <= r["tokens"] <= 2048 and r["full_support"] in (0, 1)
                assert all(0 <= r[f] <= 1 for f in ("coverage", "density", "f1"))
    for p in ("prefix", "skip"):
        groups_same = [micro["fine_read/" + p], micro["fine_lextrain/" + p]]
        groups_same.extend(s[p + "/dense"] for s in factor.values())
        for panel in groups_same:
            assert all(abs(panel[q][f] - typed["dense/" + p][q][f]) < 1e-12 for f in FIELDS for q in extra)

    arms = [("typed/train/role_degrees", typed["train/role_degrees/prefix"], "prefix"),
            ("typed/dev/role_degrees", typed["dev/role_degrees/prefix"], "prefix")]
    for cohort, content in factor.items():
        for name in ("factor", "degree"):
            arms.append(("factor/" + cohort + "/" + name, content["prefix/" + name], "prefix"))
    for stage in ("fine_read", "fine_lextrain"):
        arms.append(("micro/" + stage + "/ratio", micro[stage + "/ratio"], "skip"))
    estimates = {}
    for g, questions in groups.items():
        estimates[g] = {name: paired(rows, typed["dense/" + p], questions) for name, rows, p in arms}
    official = read(TYPED / "results.json")
    for g in groups:
        primary = estimates[g]["typed/train/role_degrees"]
        prev = official[g + "/prefix"]["pairs"]["train/role_degrees-dense"]["full_support"]
        assert np.allclose(primary["effects"]["full_support"], [prev["delta"], *prev["ci"]], atol=1e-12, rtol=0)
        assert primary["wins"] == prev["win"] and primary["losses"] == prev["loss"]
    return {"rank_sha256": rank_hash, "outcome_sha256": {f.relative_to(ROUND).as_posix(): digest(f) for f in files},
            "common_baselines_verified": True, "label": "additional historical development questions", "results": estimates}


def fmt(x):
    return f"{x:.2f}".replace(".", ",")


def interval(cell, field):
    point, lo, hi = (100 * v for v in cell["effects"][field])
    return f"{fmt(point)} [{fmt(lo)} … {fmt(hi)}]"


def report(result):
    cells = result["results"]
    labels = {"typed/train/role_degrees":"Ранг + роль + степени, обучение на train, префикс",
              "typed/dev/role_degrees":"Ранг + роль + степени, обучение на dev500, префикс",
              "micro/fine_read/ratio":"Микроблоки p/c, обучение на dev500, добор",
              "micro/fine_lextrain/ratio":"Микроблоки p/c, обучение на лексических рангах train, добор"}
    for co in ("hash64","availability"):
        for n, text in (("factor","Структура целиком"),("degree","Только степени")):
            labels["factor/" + co + "/" + n] = text + f" + калиброванный ранг, {co}, префикс"
    header = "| Метод | Полное свидетельство, метод / Dense | Δ Full Support, п.п. [95% ДИ] | Выигрыши / потери | Δ Coverage, п.п. [95% ДИ] |"
    parts = ["# Проверка переноса на 80 вопросах ISETrace",
             "Зафиксированные правила оценены на полном остатке официального dev после исключения 500 вопросов калибровки Dense-FT. Вопросы принадлежат 74 траекториям. У 27 вопросов из 21 траектории весь источник впервые встречается относительно dev500. На 53 общих траекториях по одному дополнительному вопросу. Все 74 траектории отсутствуют в исходном train и основном test. Ранее в проекте метрики других методов считались на полном dev580. Панель служит дополнительной проверкой внутри того же бенчмарка.",
             "Full Support равен единице, когда извлечены все размеченные символы свидетельств вопроса. Сравнение сохраняет родительский Dense-FT, множество кандидатов и 2 048 токенов. Для префикса целых узлов чтение заканчивается перед первым непомещающимся узлом. В контроле для микроблоков читатель Dense продолжает добор целых узлов в остаток. Всюду используется парный процентильный bootstrap по траекториям, 10 000 повторов, seed 13. Знаменатель — вопросы. Интервалы для нескольких гипотез и подгрупп приведены без поправки на множественность.",
             "Первичные сравнения отдельных протоколов — роль и степени по исходному train, факторизованный prior с hash64 и отношение полезности микроблока к цене p/c по dev500. Остальные строки помогают интерпретировать механизм."]
    for g,title in (("all","Все 80 вопросов"),("novel","27 вопросов с новыми источниками"),("shared","53 вопроса с общими источниками")):
        tab = [header,"|---|---:|---:|---:|---:|"]
        for name, c in cells[g].items():
            tab.append(f"| {labels[name]} | {c['hits']} / {c['base_hits']} из {c['n']} | {interval(c,'full_support')} | {c['wins']} / {c['losses']} | {interval(c,'coverage')} |")
        parts.extend(["## "+title,"\n".join(tab)])
    parts.extend(["Полный набор метрик включает F1, плотность свидетельства, число токенов и исходы по каждому вопросу. Контроль сверяет два способа расчёта пересечения интервалов. Дополнительная проверка сверяет попарно Full Support, Coverage, Density, F1 и токены исходного Dense во всех таблицах. [Схема разбиения](../typed_reader/holdout80/source-plan.json) · [Совпадения полей и число событий](STRATA_RU.md) · [Парные оценки](cross-reader-audit.json) · [Все микроблоки](results.json) · [Типизированный граф](../typed_reader/holdout80/results.json) · [Факторизованный prior](../factor_reader/REPORT_RU.md)",
                  "Для воспроизведения сначала нужны траектории, обученные веса исходного E5 и плотные ранги запечатанного основного теста из соседних серий. Скрипт replay.ps1 использует локальные FP32-векторы, восстанавливает недостающие в отдельном SQLite на CPU и проверяет хеши. Он сначала фиксирует прогнозы всех доступных весов, затем открывает разметку. Для повторного аудита уже полученных исходов достаточно validate_transfer.py, отчётов соседних методов и оригинального списка разбиений. [Запуск](replay.ps1) · [Первичный протокол](PROTOCOL_RU.md)"])
    (HERE / "REPORT_RU.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    res = audit()
    write(HERE / "cross-reader-audit.json", res)
    report(res)
    print("All admitted reader records, common baselines, split identities and paired estimates verified.")

