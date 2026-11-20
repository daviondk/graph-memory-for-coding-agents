"""Compare the human-readable table cells to the underlying scientific results."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent


def data(name):
    return json.loads((root.parent / name).read_text(encoding="utf-8-sig"))


def rows(file):
    cells = [line.strip().strip("|").split("|") for line in
             (root/"pages"/file).read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    return {rec[0].strip(): [v.strip() for v in rec[1:]] for rec in cells}


def number(text):
    return float(text.replace(" ", "").replace(",", ".").replace("%", "").replace("−", "-"))


def near(text, value, decimals):
    assert abs(number(text) - value) <= .500001 * 10**(-decimals), (text, value)


def audit():
    checked = []
    transfer = data("reader/transfer/results.json")
    tab = rows("03-transfer.md")
    for label, key in [("Из Cal500, без настройки","ser_full"),
                       ("Из CAsT 2020, без настройки","cast_full"),
                       ("Пропускать первый вопрос","skip_first")]:
        values, row = tab[label], transfer[key]
        assert number(values[0]) == row["reads"]
        near(values[1], row["primary"]["gate"], 5)
        near(values[2], row["secondary"]["gate"], 5)
        near(values[3], row["primary"]["gain"], 5)
    checked.append("CAsT 2021 transferred policies")
    old = data("reader/results.json")
    tab = rows("02-reader.md")
    for label, key in [("CAsT → CAsT","cast_nested"),("Cal500 → CAsT","ser_to_cast"),
                       ("Cal500 → Cal500","ser_nested"),("CAsT → Cal500","cast_to_ser")]:
        row = old[key]
        for text, target in zip(tab[label][:3], ["off","on","gate"]):
            scale, places = (100,1) if "%" in text else (1,4)
            near(text, scale * row["primary"][target], places)
        assert tab[label][3] == f"{row['saved']}/{row['n']}"
    checked.append("SERBench and CAsT 2020 paired conditions")
    stale = data("literature/results.json")["results"]
    tab = rows("04-stale.md")
    for label, key in [("Qwen2.5-14B","qwen2.5:14b"),("GLM-4.6","glm-4.6")]:
        row = stale[key]["overall"]
        for text, target in zip(tab[label], ["never","always","selected","uniform_expected_correct"]):
            near(text, row[target], 2)
    checked.append("StaleBench dated and undated results")
    tab = rows("04b-calibration.md")
    slopes = data("reader/calibration/results.json")["policies"]["relation"]
    for label, key in [("Заранее выбранный для читателя знак","fixed_reader_sign"),
                       ("Подбор только знака по 32 фактам","32/calibrated_sign"),
                       ("Общая линейная модель по 32 фактам","32/shared_ridge"),
                       ("Отдельная линейная модель по 32 фактам","32/reader_ridge")]:
        for j, reader in enumerate(["qwen2.5:14b", "glm-4.6"]):
            near(tab[label][j], 100*slopes[key][reader]["mean_accuracy"], 2)
    checked.append("StaleBench reader calibration")
    validity = data("validity/results.json")["totals"]
    tab = rows("05-validity.md")
    for label, key in [("Все изменённые файлы","all"),("Фильтр всех затронутых имён","touched"),
                       ("Фильтр чистого изменения числа","net"),("Фильтр с направлением изменения","signed"),
                       ("Четырёхбитные счётчики Count-Min","count"),("Фильтр точных смен присутствия","flips"),
                       ("Точные изменения без лимита","exact"),("Битовая маска для подписанных запросов","subscriptions")]:
        for j, cohort in enumerate(["primary","agent"]):
            assert number(tab[label][j]) == validity[cohort]["512"][key]["files"]
        near(tab[label][2], validity["agent"]["512"][key]["bytes"] / 1e6, 2)
    checked.append("Git transition reads and source bytes")
    chain = data("literature/chains/write/results.json")
    tab = list(rows("05b-chains.md").values())[1:]
    assert [int(r[0]) for r in tab] == [
        chain["methods"]["3/confirmation"]["hits"], chain["methods"]["3/protect"]["hits"], chain["any_history_hits"]]
    cue = data("literature/chains/cue/results.json")
    chain_text = (root/"pages/05b-chains.md").read_text(encoding="utf-8")
    for key in ["path", "recency", "stable8", "latest8", "full_latest"]:
        assert str(cue["methods"][key]["hits"]) in chain_text
    strict = data("literature/chains/gate/strict_results.json")
    chronology = strict["inventory"]["chronological"]
    assert chronology["usable"] == 218 and str(chronology["usable"]) in chain_text
    assert str(chronology["link_status"]["too_late"]) in chain_text
    for method in ["path", "gate", "recency"]:
        assert str(strict["comparison"]["chronological_merged"]["all"]["methods"][method]["hits"]) in chain_text
    checked.append("ChainSWE file pointer hit counts and strict SWE Context Bench transfer")
    stream = data("validity/stream/results.json")["total"]["regular"]
    for (label, values), key in zip(list(rows("06-stream.md").items())[1:], ["delta","flips","pull","lease","bloom"]):
        row = stream[key]
        assert list(map(number, values)) == [row["enrollment_bytes"],row["traffic"],row.get("roundtrips",0)]
    checked.append("Git stream registration, traffic, and round trips")
    admission = data("validity/admission/results.json")["cohorts"]["all"]
    tab = list(rows("06b-admission.md").values())[1:]
    for values, key in zip(tab, ["lru", "twohit", "edit_twohit", "uniform_exact"]):
        rec = admission["cmd/4/" + key]
        for v, metric in zip(values, ["hits", "after_edit_hits", "enrollments"]):
            near(v, rec[metric], 2)
    checked.append("SWE-smith actual key reuse and enrollment load")
    repair = data("repair/results.json")
    entries = list(rows("07-qwen.md").items())[1:]
    keys = ["version_note","blind_note","uncertainty_note","hybrid_note","version_raw","never_note","always_current"]
    assert len(entries) == len(keys)
    for (_, values), key in zip(entries, keys):
        arms = [repair["author"][c]["policy"][key] for c in ["primary","replication"]]
        assert list(map(number, values[:2])) == [a["solve"] for a in arms]
        assert list(map(number, values[2].split("/"))) == [a["rereads"] for a in arms]
    for (_, values), cohort in zip(list(rows("08-enhanced.md").items())[1:], ["primary","replication"]):
        row = repair["enhanced"][cohort]
        assert list(map(number, values[:2])) == [row["policy"][key]["solve"] for key in ["version_note","blind_note"]]
        primary = row["contrast"]["version_note-vs-blind_note"]
        assert list(map(number, values[2].split("/"))) == [primary["wins"],primary["losses"]]
        assert number(values[-1]) == primary["p"]
    checked.append("MBPP solutions, rereads, MBPP+ pairs, and exact p")
    concord = data("concord/controls/results.json")["arms"]
    tab = list(rows("08b-concord.md").values())[1:]
    assert len(tab) == 5
    for values, key in zip(tab, ["raw", "system_alert", "git", "block_context", "oracle"]):
        arm = concord[key]
        near(values[0], arm["em"], 0)
        near(values[1], arm["mean_f1"], 3)
        assert list(map(number, values[2].split("/"))) == [arm["blinded_judge_correct"], arm["judge_available"]]
        assert list(map(number, values[3].split("/"))) == [arm["prompt"], arm["completion"]]
    checked.append("All five official Concord policies, scores, semantic judgements and token costs")
    highlight = data("concord/highlight/results.json")["arms"]
    table = list(rows("08c-highlight.md").values())[1:]
    for values, key in zip(table, ["baseline", "correction", "control"]):
        for v, metric, places in zip(values, ["em", "f1", "read_file", "prompt"], [0,5,0,0]):
            near(v, highlight[key][metric], places)
    checked.append("Concord matched text highlight and control")
    return checked


if __name__ == "__main__":
    print("\n".join(audit()))
