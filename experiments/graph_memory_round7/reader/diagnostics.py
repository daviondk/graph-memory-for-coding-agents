"""Exploratory funnel from candidate file to coverage, generated edit path and target tests.
This decomposition was specified during inference without reading model replies or gold patches.
"""
from pathlib import Path
import pilot
D = pilot.D
def main():
    grade = pilot.dependency()
    assignments = pilot.read(D/"assign.json")
    inputs = pilot.read(D/"input_lock.json")
    rows = []
    for task in inputs["ids"]:
        pred = pilot.read(pilot.LOC/"predictions"/(task+".json.gz"))
        out = D/"tasks"/task/"grades_v2"
        control = pilot.read(out/"control.json")
        graded = pilot.read(out/"solver.json")
        lines = {(p,n) for p,ln in control["gold"]["gold_lines"].items() for n in ln}
        files = {p for p,n in lines}
        record = {"id":task,"gold_file_in_pool":bool(files & set(pred["paths"])),"arms":{}}
        for alias,arm in pilot.NAMES.items():
            bag = pred["arms"][arm]
            available = {(p,n) for p,start,end in bag["kept"] for n in range(start,end+1)}
            key = assignments[task][alias]
            text = pilot.read(D/"calls"/(key+".json.gz"))["response"]["choices"][0]["message"]["content"]
            try:
                edits = grade.changes(text)
                predicted = {e.get("path") for e in edits if isinstance(e,dict)}
            except (TypeError,KeyError,ValueError):
                predicted = set()
            record["arms"][arm] = {"tokens":bag["tokens"], "gold_line_in_context":bool(available & lines),
                "gold_file_proposed":bool(predicted & files), "paths_proposed":sorted(str(x) for x in predicted),
                "application_reason":graded[alias]["reason"]}
        rows.append(record)
    summary={"gold_file_in_pool":sum(r["gold_file_in_pool"] for r in rows),"arms":{}}
    for arm in pilot.NAMES.values():
        summary["arms"][arm] = {k:sum(r["arms"][arm][k] for r in rows) for k in ["gold_line_in_context","gold_file_proposed","tokens"]}
    pilot.save(D/"diagnostics.json",{"summary":summary,"rows":rows})
    print(summary)
if __name__=="__main__":main()
