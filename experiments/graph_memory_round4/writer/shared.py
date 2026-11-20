"""Locations and established R3 projector/evaluator. Never execute input trace text."""
import gzip,hashlib,json,sys
from pathlib import Path

D=Path(__file__).resolve().parent
WORK=D.parents[1]
R3=WORK/"graph_memory_round3"
A=R3/"real_swe"; B=R3/"real_swe_followup"
sys.path.insert(0,str(B))
import writer_followup as prior
sys.path.insert(0,str(R3/"context"))
from context import stream,future,line_target
from common import printed

def read(path): return json.loads(Path(path).read_bytes())
def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=True,indent=1),encoding="utf8")
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path):
    with gzip.open(path,"rt",encoding="utf8") as file:
        for line in file: yield json.loads(line)
def write(file,value): file.write(json.dumps(value,ensure_ascii=True,separators=(",",":"))+"\n")

