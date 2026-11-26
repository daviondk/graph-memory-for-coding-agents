"""Create a code-only memory benchmark without using the masked implementation as retrieval input."""
import ast
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,math,os,re,sys,textwrap
from urllib.request import urlopen

D=Path(__file__).resolve().parent
R52=D.parents[1]/"graph_memory_round52"
WORK=Path("D:/CodexResearch/x20-r54-execution")
DATA=WORK/"ClassEval_data.json"
REV="eaeac44d0d5dcd8a95feec50726d66fedc73a98f"
SOURCE_HASH="50a1ac0e4d0c238573c10c0ab11feae00b14a80ae9e4c9cc28148707ecf0b6a2"
IMAGE="sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30"
ALLOWED_CLASSES=set("""AreaCalculator ArgumentParser ArrangementCalculator AssessmentSystem AutomaticGuitarSimulator AvgPartition BalancedBrackets BankAccount BigNumCalculator BinaryDataProcessor BitStatusUtil BlackjackGame BookManagement BoyerMooreSearch Calculator CalendarUtil CamelCaseMap ChandrasekharSieve Classroom ClassRegistrationSystem CombinationCalculator ComplexCalculator CurrencyConverter DataStatistics DataStatistics2 DataStatistics4 DiscountStrategy EightPuzzle FitnessTracker GomokuGame Hotel HRManagementSystem Interpolation JobMarketplace KappaCalculator LongestWord MahjongConnect Manacher MetricsCalculator MetricsCalculator2 MovieBookingSystem MusicPlayer NumberConverter NumberWordFormatter NumericEntityUnescaper Order PageUtil PersonRequest PushBoxGame RegexUtils RPGCharacter ShoppingCart Snake SplitSentence Statistics3 StockPortfolioTracker Thermostat TicTacToe TimeUtils TriCalculator TwentyFourPointGame VendingMachine Warehouse WeatherSystem Words2Numbers""".split())
IMPORTS=set("bisect calendar collections copy datetime decimal enum fractions functools heapq itertools json math operator random re statistics string time typing unittest".split())
BANNED=set("open eval exec compile __import__ breakpoint input exit quit globals locals vars getattr setattr delattr os sys subprocess socket requests ctypes pathlib pickle marshal builtins importlib".split())
SIGNS=set("get set self return para param example true false int str float list dict the a an are it in to of or for with is class def and method this that from as".split())
ARMS=("caller_bm25","bm25","contract")
def hash_bytes(b):return hashlib.sha256(b).hexdigest()
def sha(path):return hash_bytes(path.read_bytes())
def read(path):
    blob=path.read_bytes();return json.loads(gzip.decompress(blob) if path.suffix==".gz" else blob)
def put(name,obj):
    path=D/name
    data=(json.dumps(obj,sort_keys=True,ensure_ascii=False,indent=None if path.suffix==".gz" else 2,allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)
def get(name):return read(D/name)
def dataset():
    WORK.mkdir(exist_ok=True,parents=True)
    if not DATA.exists():
        DATA.write_bytes(urlopen(f"https://raw.githubusercontent.com/FudanSELab/ClassEval/{REV}/data/ClassEval_data.json",timeout=40).read())
    assert sha(DATA)==SOURCE_HASH
    return read(DATA)
def safe(tree):
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            names=[x.name for x in n.names] if isinstance(n,ast.Import) else [n.module or ""]
            if any(k.split(".")[0] not in IMPORTS for k in names):return False
        if isinstance(n,ast.Name) and n.id in BANNED:return False
        if isinstance(n,ast.Attribute) and (n.attr in BANNED or n.attr in ("__class__","__dict__","__globals__","__subclasses__","__getattribute__","__code__")):return False
    return True
def terms(text):
    out=[]
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_]*",text):
        raw=tok.lower()
        if raw not in SIGNS:out.append(raw)
        split=re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+",tok)
        out.extend(t.lower() for t in split if t.lower()!=raw and t.lower() not in SIGNS)
    return out
def rank(query,documents):
    doc={k:Counter(terms(txt)) for k,txt in documents.items()};n=len(doc);dl={k:sum(v.values()) for k,v in doc.items()};avg=sum(dl.values())/n
    scores={k:0. for k in doc}
    for term,tfq in Counter(terms(query)).items():
        df=sum(term in bag for bag in doc.values());idf=math.log1p((n-df+.5)/(df+.5))
        for k,bag in doc.items():
            f=bag[term]
            if f:scores[k]+=tfq*idf*2.2*f/(f+1.2*(.25+.75*dl[k]/max(1,avg)))
    return sorted(scores,key=lambda k:(-scores[k],k))
def snippet(fn):
    node=ast.parse(ast.unparse(fn)).body[0]
    if ast.get_docstring(node) is not None:node.body=node.body[1:]
    return ast.unparse(node) if node.body else ""
def signature(fn):
    return f"{fn.name}({ast.unparse(fn.args)})"
def call_edge(fn,target,classname):
    return any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr==target and
      isinstance(n.func.value,ast.Name) and n.func.value.id in ("self","cls",classname) for n in ast.walk(fn))
def class_node(src,name):
    return next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name==name)
def enumerate_candidates():
    reasons=Counter();entries={};cases={}
    for row in dataset():
        cls=row["class_name"]
        if cls not in ALLOWED_CLASSES:reasons["class_not_in_benign_allowlist"]+=1;continue
        try:t=ast.parse(row["solution_code"]);tests=ast.parse(row["test"])
        except SyntaxError:reasons["class_unparseable"]+=1;continue
        if not safe(t) or not safe(tests):reasons["class_import_or_operation_not_allowed"]+=1;continue
        node=class_node(row["solution_code"],cls)
        methods={m.name:m for m in node.body if isinstance(m,ast.FunctionDef)}
        infos={v["method_name"]:v for v in row["methods_info"]}
        for target,info in infos.items():
            if target.startswith("__") or target not in methods:reasons["ineligible_method_name"]+=1;continue
            # Only other methods can supply snippets, rankings or reverse edges.
            visible={k:v for k,v in methods.items() if k!=target and not k.startswith("__") and k in infos}
            callers=[k for k,v in visible.items() if call_edge(v,target,cls)]
            if len(visible)<2 or not callers:reasons["too_few_siblings_or_no_observed_caller"]+=1;continue
            contract=info["method_description"].strip()
            documents={k:k+"\n"+infos[k]["method_description"]+"\n"+snippet(v) for k,v in visible.items()}
            # Code and docs of the target's SOURCE implementation are never included.
            ordering=rank(cls+" "+target+" "+contract,documents)
            name=row["task_id"]+"|"+cls+"."+target
            fields=", ".join(map(str,row["fields"]))
            task=("Class "+cls+"\n"+row["class_description"].strip()+"\nDeclared fields: "+fields+
              "\nAvailable sibling signatures:\n"+"\n".join(signature(v) for v in visible.values())+
              "\nTarget method contract:\n"+contract)
            top=ordering[0];edge=next(k for k in ordering if k in callers)
            entries[name]=dict(cls=cls,method=target,task_id=row["task_id"],test_class=info["test_class"],task=task,
                imports=row["import_statement"],rank=ordering,callers=sorted(callers),choices=dict(caller_bm25=edge,bm25=top),
                evidence={k:snippet(visible[k]) for k in {edge,top}})
            cases[name]=row
    return entries,cases,reasons
def patched(row,target,body):
    # Replace the original target implementation before serializing the program for the test runner.
    root=ast.parse(row["solution_code"])
    cls=next(n for n in root.body if isinstance(n,ast.ClassDef) and n.name==row["class_name"])
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==target)
    fn.body=body
    return ast.unparse(ast.fix_missing_locations(root))
def select():
    from isolate import execute
    entries,cases,reasons=enumerate_candidates()
    jobs=[]
    for k,r in entries.items():
        row=cases[k]
        for design,src in [("reference",row["solution_code"]),("blank",patched(row,r["method"],ast.parse("raise NotImplementedError()").body))]:
            jobs.append(dict(id=k+"|"+design,src=src,test=row["test"],suite=r["test_class"]))
    print("Reference and blank controls",len(jobs),flush=True)
    labels=execute(jobs,4);counts=Counter();keep=[]
    for k in sorted(entries,key=lambda x:hash_bytes(("r54-class-pair|"+x).encode())):
        rr=labels[k+"|reference"];zz=labels[k+"|blank"]
        if not rr.get("passed") or rr["run"]==0:reasons["reference_failed_or_empty"]+=1;continue
        if rr["run"]!=zz.get("run") or zz["passed"]:reasons["blank_not_tested"]+=1;continue
        if counts[entries[k]["cls"]]>=4 or len(keep)>=80:reasons["registered_caps"]+=1;continue
        counts[entries[k]["cls"]]+=1;keep.append(k)
    put("calibration.json.gz",labels)
    put("observations.json.gz",{k:entries[k] for k in keep})
    put("selection.json",dict(n=len(keep),classes=dict(counts),reasons=dict(reasons),structural=len(entries),cases=keep,
         observations=sha(D/"observations.json.gz"),controls=sha(D/"calibration.json.gz"),protocol=sha(D/"PROTOCOL_RU.md"),
         code=sha(Path(__file__)),runner=sha(D/"isolate.py"),source=SOURCE_HASH,docker=IMAGE))
    print("Sealed sample",len(keep),len(counts),dict(reasons),flush=True)
if __name__=="__main__":select()
