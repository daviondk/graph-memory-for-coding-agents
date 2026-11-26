from collections import Counter,defaultdict
import numpy as np
from shared import D,read,sha,save


def summary(rows,checks):
    counts=Counter();text=Counter();issues=defaultdict(list)
    for r in rows:
        obs=checks[r["run"],r["at"]]
        counts.update(r["cost"])
        counts.update(dict(records=1,range_reuse=r["same"],file_reuse=r["file_same"],stable_coordinates=r["stable"],
            empty_old=int(not r["old"]),empty_after_interval=int(not r["interval"]),
            absent_selected_affected=int(r["cost"]["old_selected_affected"]==0),
            no_target_in_pool=int(obs.get("retained_lines",0)==0),
            counted_reuse_with_target=int(r["same"] and r["cost"]["old_selected_affected"]>0)))
        text.update(obs)
        issues[r["issue"]].append(r["same"]-r["file_same"])
    vals=np.asarray([np.mean(issues[i]) for i in sorted(issues)])
    boot=np.random.default_rng(401113).choice(vals,(10000,len(vals))).mean(axis=1)*100
    all_rows,all_bytes=counts["all_pool_rows"],counts["all_pool_bytes"]
    correct_lines=text["removed_lines"]-text["removed_wrong_lines"]
    correct_bytes=text["removed_bytes"]-text["removed_wrong_bytes"]
    unknown_rows=counts["removed_rows"]-text["removed_lines"]
    unknown_bytes=counts["removed_bytes"]-text["removed_bytes"]
    return dict(counts=counts,text=text,issues=len(vals),range_minus_file_issue_macro_pp=100*vals.mean(),
        interval95_pp=np.quantile(boot,[.025,.975]).tolist(),coverage=dict(
        remaining_rows=all_rows-counts["removed_rows"],remaining_bytes=all_bytes-counts["removed_bytes"],
        retained_row_fraction=1-counts["removed_rows"]/all_rows,retained_byte_fraction=1-counts["removed_bytes"]/all_bytes,
        target_verified_correct_removed_rows=correct_lines,target_verified_correct_removed_bytes=correct_bytes,
        other_path_unverified_removed_rows=unknown_rows,other_path_unverified_removed_bytes=unknown_bytes,
        total_correct_removed_rows_bounds=[correct_lines,correct_lines+unknown_rows],
        total_correct_removed_bytes_bounds=[correct_bytes,correct_bytes+unknown_bytes]))


def main():
    checks={(run,at):c for run,at,c in read(D/"checked-text.json.gz")}
    all_rows=read(D/"selections.json.gz")
    assert set(checks)=={(r["run"],r["at"]) for r in all_rows}
    filters={"holdout":lambda r:r["held"],"all":lambda r:True,"main":lambda r:r["group"]=="main",
        "holdout_main":lambda r:r["held"] and r["group"]=="main","discovery":lambda r:not r["held"],
        "holdout_nonempty_target":lambda r:r["held"] and r["cost"]["old_selected_affected"]>0,
        "all_nonempty_target":lambda r:r["cost"]["old_selected_affected"]>0}
    out={k:summary([r for r in all_rows if f(r)],checks) for k,f in filters.items()}
    by_issue={}
    for issue in sorted({r["issue"] for r in all_rows}):
        ss=[r for r in all_rows if r["issue"]==issue]
        by_issue[issue]=[ss[0]["held"],len(ss),sum(r["same"] for r in ss),sum(r["file_same"] for r in ss)]
    save(D/"results.json",dict(strata=out,issue_counts=by_issue,bootstrap=10000,seed=401113,selection=sha(D/"selection-seal.json"),
        text_check=sha(D/"text-check.json"),implementation=sha(D/"analyze.py")))
    for k,r in out.items():
        print(k,r["issues"],r["counts"]["records"],r["counts"]["range_reuse"],r["counts"]["file_reuse"],
              r["range_minus_file_issue_macro_pp"],r["interval95_pp"],r["coverage"])


if __name__=="__main__":
    main()
