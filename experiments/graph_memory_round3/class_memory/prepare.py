import ast,concurrent.futures,ctypes,json,subprocess,sys,textwrap
from ctypes import wintypes
from common import D,ROOT,read,save,sha
class Limits(ctypes.Structure):
    _fields_=[("user",ctypes.c_int64),("job",ctypes.c_int64),("flags",ctypes.c_uint32),("lo",ctypes.c_size_t),("hi",ctypes.c_size_t),("active",ctypes.c_uint32),("affinity",ctypes.c_size_t),("priority",ctypes.c_uint32),("sched",ctypes.c_uint32)]
class Info(ctypes.Structure):
    _fields_=[("limits",Limits),("io",ctypes.c_uint64*6),("process_mem",ctypes.c_size_t),("job_mem",ctypes.c_size_t),("peak_proc",ctypes.c_size_t),("peak_job",ctypes.c_size_t)]
def execute(data):
    k=ctypes.windll.kernel32;k.CreateJobObjectW.restype=wintypes.HANDLE
    k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.CloseHandle.argtypes=[wintypes.HANDLE]
    process=subprocess.Popen([sys.executable,"-I","-B","-S",str(D/"worker.py")],cwd=D,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    job=k.CreateJobObjectW(None,None)
    try:
        v=Info();v.limits.flags=0x2100;v.process_mem=192*1024*1024
        assert job and k.SetInformationJobObject(job,9,ctypes.byref(v),ctypes.sizeof(v)) and k.AssignProcessToJobObject(job,int(process._handle))
        raw=process.communicate(json.dumps(data).encode(),timeout=6)[0];return json.loads(raw.splitlines()[-1])
    except (subprocess.TimeoutExpired,ValueError,IndexError) as exc:return {"status":"process","why":type(exc).__name__}
    finally:
        if process.poll() is None:process.kill();process.wait()
        if job:k.CloseHandle(job)
SAFE=set("AreaCalculator ArgumentParser ArrangementCalculator AssessmentSystem AutomaticGuitarSimulator AvgPartition BalancedBrackets BankAccount BigNumCalculator BinaryDataProcessor BitStatusUtil BookManagement BoyerMooreSearch Calculator CalendarUtil CamelCaseMap ChandrasekharSieve Classroom ClassRegistrationSystem CombinationCalculator ComplexCalculator CurrencyConverter DataStatistics DataStatistics4 DiscountStrategy EightPuzzle ExpressionCalculator FitnessTracker GomokuGame Hotel HRManagementSystem Interpolation JobMarketplace LongestWord MahjongConnect Manacher MetricsCalculator MusicPlayer NLPDataProcessor NLPDataProcessor2 NumberConverter NumberWordFormatter NumericEntityUnescaper Order PageUtil ShoppingCart SplitSentence Statistics3 StockPortfolioTracker TicTacToe TriCalculator VendingMachine Warehouse WeatherSystem Words2Numbers".split())
def taskid(r,m):return r["task_id"]+"/"+m["method_name"]
def grade_input(r,m):
    return {"class":r["class_name"],"name":m["method_name"],"source":r["solution_code"],"imports":r["import_statement"],"tests":m["test_code"],"testclass":m["test_class"]}
def check_row(raw):
    r,idx,m=raw;blob=grade_input(r,m);base=execute({**blob,"grade":"reference"});stub=execute({**blob,"grade":"stub"})
    return (taskid(r,m),idx,base,stub)
def method_body(src):
    f=ast.parse(textwrap.dedent(src)).body[0]
    if f.body and isinstance(f.body[0],ast.Expr) and isinstance(f.body[0].value,ast.Constant) and isinstance(f.body[0].value.value,str):f.body.pop(0)
    return ast.unparse(f)
def interface(m):
    line=next((s.strip() for s in m["method_description"].splitlines() if s.strip().startswith("def ")),m["method_name"])
    return line
def main():
    ds=D/"ClassEval_data.json";assert sha(ds.read_bytes())=="50a1ac0e4d0c238573c10c0ab11feae00b14a80ae9e4c9cc28148707ecf0b6a2"
    raw=read(ds);cand=[(r,j,m) for r in raw if r["class_name"] in SAFE for j,m in enumerate(r["methods_info"]) if j and not m["method_name"].startswith("__")]
    with concurrent.futures.ThreadPoolExecutor(6) as pool:checks={i:(j,b,s) for i,j,b,s in pool.map(check_row,cand)}
    save(D/"calibration.json",checks);classes={};kept=[]
    for r,j,m in cand:
        i=taskid(r,m);_,ref,stub=checks[i]
        if ref.get("status")!="pass" or ref.get("skipped") or stub.get("status")!="fail" or stub.get("total")!=ref.get("total"):continue
        cls_node=next(z for z in ast.parse(r["solution_code"]).body if isinstance(z,ast.ClassDef) and z.name==r["class_name"])
        past={f.name:f for f in cls_node.body if isinstance(f,ast.FunctionDef) and f.name in {h["method_name"] for h in r["methods_info"][:j]}}
        if any(h["method_name"] not in past for h in r["methods_info"][:j]):continue
        prev=[{"method":h["method_name"],"src":method_body(ast.unparse(past[h["method_name"]]))} for h in r["methods_info"][:j]]
        constructor=r["class_constructor"]
        point=dict(id=i,cls=r["class_name"],name=m["method_name"],desc=m["method_description"],summary=r["class_description"],imports=r["import_statement"],constructor=constructor,
                   interfaces=[interface(h) for h in r["methods_info"]],previous=prev)
        classes.setdefault(r["class_name"],[]).append(point)
    for v in classes.values():kept.extend(sorted(v,key=lambda x:(-min(3,len(x["previous"])),sha("choose|"+x["id"])))[:4])
    kept=sorted(kept,key=lambda x:sha("r3-class|"+x["id"]))[:108]
    save(D/"visible.json",kept);save(D/"roster.json",{"total_precontrol":len(cand),"passed_controls":sum(b["status"]=="pass" and s["status"]=="fail" for j,b,s in checks.values()),"chosen":len(kept),"classes":len({x['cls'] for x in kept}),"ids":[x['id'] for x in kept]})
    print(len(cand),len(kept),len({x['cls'] for x in kept}),flush=True)
if __name__=="__main__":main()

