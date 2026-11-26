import sys
from pathlib import Path
from datetime import datetime,timezone
import json
D=Path(__file__).resolve().parent
CURVE=D.parent/"budget_curve"
sys.path.insert(0,str(CURVE))
from common import W,GLOBAL,REMAIN,SEEDS,BUDGETS,read,save,sha
ORDERS=("full_rgcn","wo_chunk_adjacency")
RULES=("strict","firstfit","graph_dp","graph_density","graph_value","rank_dp","dense_dp","graph_dp_equal_spend")


def log(kind,**fields):
    with (D/"run-log.jsonl").open("a",encoding="utf-8") as f:
        f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),event=kind,**fields),sort_keys=True)+"\n")
