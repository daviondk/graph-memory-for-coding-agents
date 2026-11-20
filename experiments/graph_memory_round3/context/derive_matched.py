"""Produce a reviewable derivative of the frozen policy; only the two per-action token caps change."""
from pathlib import Path
D=Path(__file__).resolve().parent
source=(D/"predict.py").read_text(encoding="utf8")
replacements=[
 ('BUDGETS=(256,512)','BUDGETS=(512,)'),
 ('        old,recent=baselines[B]\n        best=', '''        old,recent=baselines[B]
        original=payload(old);charged_limit,wire_limit=original[1:]
        recent_selected=[]
        for j in range(len(idx)):
            u=start[j]
            trial=(*recent_selected,u)
            data=payload(trial)
            if data[1]<=charged_limit and data[2]<=wire_limit:recent_selected.append(u)
            if len(recent_selected)==3:break
        recent=tuple(recent_selected)
        best='''),
 ('for u in us))<=B:', 'for u in us))<=wire_limit:'),
 ('if c>B:continue','if c>charged_limit:continue'),
 ('if zprice+c>B:continue','if zprice+c>charged_limit:continue'),
 ('if unit_cost(u)<=B:fixed=(u,);break','if unit_cost(u)<=min(charged_limit,wire_limit):fixed=(u,);break'),
 ('q<=B and v<=B and len(z)<=3','q<=charged_limit and v<=wire_limit and len(z)<=3'),
 ('f"pred_{k}.jsonl.gz"','f"matched_pred_{k}.jsonl.gz"'),
 ('"method_lock.json"','"matched_method_lock.json"'),
 ('D/"predict.py",D/"fine_model.json"','D/"predict.py",D/"matched_policy.py",D/"MATCHED_PROTOCOL.md",D/"fine_model.json"'),
 ('"prediction_lock.json"','"matched_prediction_lock.json"'),
 ('"pred_*.gz"','"matched_pred_*.gz"')]
for a,b in replacements:
    if a not in source:raise ValueError(a)
    source=source.replace(a,b)
(D/"matched_policy.py").write_text(source,encoding="utf8")

