"""Run the published ConcordBench tool loop unchanged; customize evidence rendering in one arm."""
import os
os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
import gzip,hashlib,json,random,sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;UP=ROOT/'upstream';BENCH=UP/'bench'
os.environ['HF_HOME']=str(ROOT/'hf-cache')
sys.path[:0]=[str(UP/'src'),str(BENCH)]
import requests
from qa_agent import loop
from qa_agent.driver import load_pioneer_instance,run_instance
from qa_agent.race import RaceController,load_race_patches
from qa_agent.llm import LLMResponse,ToolCall,TokenUsage
from block_context.types import BlockState,TransformType
ORIGINAL=loop.block_context_messages
MODEL='qwen38-27b-ud-q4km'
def compact(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def save(p,x):
    temp=p.with_suffix('.tmp');temp.write_bytes(gzip.compress(compact(x),mtime=0));os.replace(temp,p)
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
class RequestLimit(Exception):pass
class Local:
    def __init__(self):
        self.requests=[];self.called=set()
    def chat(self,messages,tools):
        # Qwen's released template accepts system instructions only in the initial turn.
        # Keep the public runtime notice verbatim and in its original turn position.
        messages=[{**m,'role':'user'} if i and m['role']=='system' else m for i,m in enumerate(messages)]
        data={'model':MODEL,'messages':messages,'temperature':0,'seed':18112026,'max_tokens':256,'chat_template_kwargs':{'enable_thinking':False},'tools':tools,'tool_choice':'auto'}
        k=sha(compact(data));dest=ROOT/'calls'/(k+'.json.gz');self.requests.append(k)
        if len(self.requests)>100:raise RequestLimit('transport_loop_cap100')
        if dest.exists():r=read(dest)
        else:
            res=requests.post('http://127.0.0.1:18961/v1/chat/completions',json=data,timeout=140)
            if res.status_code not in (200,400):
                save(ROOT/'failures'/(k+'.json.gz'),{'request':data,'response':res.text,'status':res.status_code})
                res.raise_for_status()
            r={'code':res.status_code,'request':data,'response':res.json()};save(dest,r)
        if r['code']!=200:raise RequestLimit('http400 '+str(r['response'])[:220])
        resp=r['response'];m=resp['choices'][0]['message'];calls=[]
        for raw in m.get('tool_calls') or []:
            fun=raw['function']
            try:args=json.loads(fun['arguments'])
            except (TypeError,ValueError):args={}
            calls.append(ToolCall(raw['id'],fun['name'],args if isinstance(args,dict) else {}))
        use=resp['usage'];return LLMResponse(m.get('content') or '',calls,resp['choices'][0].get('finish_reason'),TokenUsage(use['prompt_tokens'],use['completion_tokens'],use['total_tokens']))
class Window:
    def __init__(self):self.cache={};self.audit=[];self.reads=0;self.bytes=0
    def __call__(self,messages,*,runtime,document,tool_evidence,**kw):
        out=ORIGINAL(messages,runtime=runtime,document=document,tool_evidence=tool_evidence,**kw)
        for j,m in enumerate(messages):
            if m.get('role')!='tool':continue
            for b in reversed(tool_evidence.get(str(m.get('tool_call_id')),())):
                block=runtime.get_block(b)
                if block.state==BlockState.VALID or block.transform_type!=TransformType.VERBATIM:continue
                src=next((x for x in block.source_set if x.span is not None),None)
                if not src:continue
                p=(runtime.workspace_root/src.object_id).resolve()
                if not p.is_relative_to(runtime.workspace_root.resolve()) or not p.is_file():continue
                generation=runtime.source_index.by_source[src.object_id].source_version
                line=src.span.start_line;ck=(src.object_id,generation,line)
                if ck not in self.cache:
                    raw=p.read_bytes();self.reads+=1;self.bytes+=len(raw)
                    lines=raw.decode('utf8').splitlines();snippet='\n'.join(lines[max(0,line-2):line+1]).encode()[:600].decode('utf8','ignore')
                    self.cache[ck]=snippet;self.audit.append({'path':src.object_id,'line':line,'bytes':len(raw),'sha256':sha(raw),'excerpt_sha':sha(snippet.encode())})
                out[j]['content']+='\nCurrent source window '+src.object_id+' near line '+str(line)+':\n'+self.cache[ck]
                break
        return out
def task(tid,arm):
    target=ROOT/'trials'/(tid+'_'+arm+'.json.gz')
    if target.exists():return
    bundle=load_pioneer_instance(tid,bench_root=BENCH,cache_dir=ROOT/'work'/'v2'/arm,opaque_doc_ids=True,max_tool_calls_per_event=1)
    race=RaceController(load_race_patches(BENCH/'patch_candidate_augmented.json',tid),delay_steps=0)
    race.apply_a_side_mutations(bundle.runtime)
    provider=Local();window=Window();loop.block_context_messages=window if arm=='window' else ORIGINAL
    z={'id':tid,'arm':arm}
    try:
        result=run_instance(bundle,provider,policy='raw' if arm=='raw' else 'block_context',max_events=30,race_controller=race)
        z.update({'answer':result.final_answer,'stop':result.stop_reason,'events':result.event_count,'actions':result.tool_call_count,'race_events':len(result.race_events),'trace':[[{'tool':c.tool_name,'arguments':c.tool_args,'observation':c.tool_result} for c in event.tool_calls] for event in result.events]})
    except RequestLimit as e:z.update({'answer':'','stop':str(e),'events':None,'actions':None,'race_events':None,'trace':[]})
    finally:loop.block_context_messages=ORIGINAL
    z.update({'requests':provider.requests,'proactive_reads':window.reads,'read_bytes':window.bytes,'fresh_windows':window.audit});save(target,z)
def main():
    for n in ('trials','calls','work','failures'):(ROOT/n).mkdir(exist_ok=True)
    rev=subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD']).decode().strip()
    assert rev=='4116936349995f0f30597931c0dbbebcbf7e58ac'
    roster=[r['id'] for r in json.loads((BENCH/'pioneer_augmented.json').read_bytes())['hotpotqa']];assert len(set(roster))==40
    order=sorted(roster,key=lambda t:sha(('concord-s6|'+t).encode()))
    design={'upstream':rev,'roster':order,'protocol':sha((ROOT/'PROTOCOL.md').read_bytes()),'implementation':sha(Path(__file__).read_bytes())}
    lock=ROOT/'input_lock_v2.json'
    if lock.exists():assert json.loads(lock.read_bytes())==design
    else:lock.write_text(json.dumps(design,indent=2))
    for n,tid in enumerate(order):
        arms=['baseline','window','raw'];random.Random('s6-order|'+tid).shuffle(arms)
        for arm in arms:task(tid,arm)
        print('completed',n+1,'/40, unique calls',len(list((ROOT/'calls').glob('*.gz'))),flush=True)
    (ROOT/'decision_lock.json').write_text(json.dumps({p.name:sha(p.read_bytes()) for p in sorted((ROOT/'trials').glob('*.gz'))},indent=1))
if __name__=='__main__':main()
