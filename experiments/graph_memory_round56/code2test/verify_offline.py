"""Verify all sealed original policies and secondary metrics from the checked-in projections."""
from math import isclose
from statistics import fmean

from grade import compare, metrics
from rank import run_case
from source import HERE, digest, read


def main():
    for name, expected_hash in read(HERE / "prediction-seal.json").items():
        assert digest(HERE / name) == expected_hash, name
    roster = read(HERE / "roster.json")
    pool = read(HERE / "catalog.json.gz")
    publisher = read(HERE / "publisher.json.gz")
    others = read(HERE / "community.json.gz")
    history = read(HERE / "histories.json.gz")
    predictions = read(HERE / "predictions.json.gz")
    grades = read(HERE / "graded.json.gz")
    gold = read(HERE / "ground-truth.json.gz")
    secondary = read(HERE / "additive-ranks.json.gz")
    secondary_grades = read(HERE / "additive-graded.json.gz")
    role_ranks = read(HERE / "role-ranks.json.gz")
    role_results = read(HERE / "role-results.json")
    role_totals = {}
    completed = 0
    for q, row in roster.items():
        if not row["eligible"]:
            continue
        base = row["base"]
        actual = run_case(row, set(pool[base]), publisher[q], others[q], history[base]["history"])
        assert actual["ranked"] == predictions[q]["ranked"], q
        for mode, methods in actual["ranked"].items():
            for method, ranked in methods.items():
                assert metrics(ranked, set(gold[q])) == grades[mode][q]["metrics"][method]
                completed += 1
        for method, ranked in secondary[q].items():
            observed = metrics(ranked, set(gold[q]))
            assert observed == secondary_grades[q]["metrics"][method][:3]
            assert int(observed[0] == 1) == secondary_grades[q]["metrics"][method][3]
        for mode, methods in role_ranks[q].items():
            for method, ranked in methods.items():
                role_totals.setdefault((mode, method), []).append(metrics(ranked, set(gold[q]))[0])
    for (mode, method), values in role_totals.items():
        assert isclose(fmean(values), role_results[mode]["means"][method][0], abs_tol=1e-12)
    for key, expected in read(HERE / "additive-results.json")["comparisons"].items():
        left, right = key.split("__")
        assert expected == compare(list(secondary_grades.values()), left, right)
    print(f"{completed} original rankings regenerated. Secondary metrics and confidence intervals verified.")


if __name__ == "__main__":
    main()
