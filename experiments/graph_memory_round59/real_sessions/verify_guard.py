"""Audit the mutation boundary and a fail-closed process generation check."""
import argparse
from collections import Counter
from replay import ARMS, HERE, Image, Reader, empty, read_json, save


def guarded(img, trusted_old, trusted_new):
    if trusted_old is None or trusted_new is None or trusted_new != trusted_old:
        return Reader(empty())
    return Reader(img)


def check_changed_fixture():
    payload = Image(14,{("dummy",1):0, ("dummy",2):0}, {})
    after_edit = [(1,300,3),(2,301,4)]
    bad = Reader(payload).window("dummy",after_edit)
    assert bad[0] == 1 and bad[-1] == 1
    for a,b in [(1,2),(1,None),(None,1),(None,None)]:
        got = guarded(payload,a,b).window("dummy",after_edit)
        assert got[0] == 2 and got[-1] == 0
    unchanged = guarded(payload,1,1).window("dummy",[(1,300,3),(2,300,3)])
    assert unchanged[0] == 1 and unchanged[-1] == 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verify",action="store_true")
    args = p.parse_args()
    check_changed_fixture()
    traces = read_json(HERE/"outcomes.json.gz")["traces"]
    counts = Counter()
    rejected = Counter()
    for r in traces:
        if r["image"]["selective"][0]:
            counts["emitted"] += 1
            if r["first_barrier"] == 0:
                counts["cleared_before_show"] += 1
            if r["first_barrier"] is None:
                counts["no_further_barrier"] += 1
        for i,w in enumerate(r["windows"]):
            if r["first_barrier"] is not None and i >= r["first_barrier"]:
                counts["windows_checked_after_barrier"] += 1
                for arm in w:
                    assert [arm[i] for i in (0,1,2,4,5)] == [w[0][i] for i in (0,1,2,4,5)]
        # Generation rejected at open, so no image or old text is read. Write already sunk.
        for a in ARMS:
            rejected[a] += r["image"][a][0] + sum(w[0][2] for w in r["windows"])
    blob = dict(counts=dict(counts), bytes_if_generation_unavailable_at_open=dict(rejected),
                source_generation_recorded=False, wrong_if_changed_fixture_trusted_blindly=1,
                wrong_if_unknown_or_changed_generation_rejected=0)
    save(HERE/"guard.json",blob,args.verify)
    print(blob)


if __name__=="__main__":
    main()
