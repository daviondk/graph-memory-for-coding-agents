from pathlib import Path
import gzip,hashlib,json,re,sys
D=Path(__file__).resolve().parent
R=D.parent/"repo"
sys.path.insert(0,str(R));sys.path.insert(0,str(D.parents[1]/"graph_memory_round3/repo/lib"))
from data_io import rows,files,panel_name
from tokenizers import Tokenizer
TOKENFILE=D.parents[1]/"memory_session5/live/tokenizer.json"
tok=Tokenizer.from_file(str(TOKENFILE))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rd(p):return json.loads((R/p).read_bytes())
def get(key):
    if key=="A":return rd("native_predictions.json"),R/"java.pred.jsonl.gz","native_roster.json"
    return rd("paired_java_cff.json")+rd("paired_java_cfr.json"),R/"strict_java.pred.jsonl.gz","paired_roster.json"
BAD=re.compile(r"\b(?:shellcode|metasploit|weaponized|ammunition|malware|bioweapon|exploit(?:s|ation)?|privilege escalation|command injection|remote code execution|bypass authentication|deserialization attack|ransomware)\b",re.I)
def trim(txt,n,tail=False):
    ids=tok.encode(txt,add_special_tokens=False).ids
    if len(ids)<=n:return txt,len(ids)
    ix=ids[-n:] if tail else ids[:n]
    # Re-tokenize the rendered string, including incomplete boundary symbols.
    val=tok.decode(ix,skip_special_tokens=False)
    while len(tok.encode(val,add_special_tokens=False).ids)>n:
        ix=ix[1:] if tail else ix[:-1];val=tok.decode(ix,skip_special_tokens=False)
    return val,len(tok.encode(val,add_special_tokens=False).ids)
def main(key):
    native,pred,roster=get(key);targets=rd(roster)
    sem={(a,i):rank[0] for a,i,l,_,rank in native if l==3}
    with gzip.open(pred,"rt",encoding="utf8") as fp:
        graph={(q[0],q[1]):q[-1]["graph"][0] for q in map(json.loads,fp) if q[2]==3 and q[1] in targets.get(q[0],[])}
    assert sem.keys()==graph.keys()
    data=[];log=[];offset={};inputsha={}
    for path in files("java","test"):
        p=panel_name(path.stem);start=offset.get(p,0);count=0;inputsha[path.name]=digest(path)
        for j,row in enumerate(rows(path,["code","context","repo_name","file_path"])):
            count+=1;idx=j+start
            if (p,idx) not in graph:continue
            keyi=p+"|"+str(idx)
            ctx,ct=trim("\n".join(row["code"].splitlines()[-3:]),512,True)
            arms={"graph":graph[p,idx],"semlith":sem[p,idx]}
            snippets={a:trim(row["context"][n],256) for a,n in arms.items()}
            if BAD.search(" ".join([row["repo_name"],row["file_path"],ctx]+[s[0] for s in snippets.values()])):
                log.append(keyi);continue
            if key=="A":snippets["empty"]=("(no external fragment)",0)
            data.append({"id":keyi,"panel":p,"global_index":idx,"repo":row["repo_name"],"file":path.name,"local_index":j,"ctx":ctx,"ctx_tokens":ct,"ranks":arms,"snippets":snippets})
        offset[p]=start+count
    assert len(data)+len(log)==len(sem)
    raw=json.dumps(data,separators=(",",":"),ensure_ascii=True).encode()
    out=D/(key+"_packets.json.gz");out.write_bytes(gzip.compress(raw,mtime=0))
    (D/(key+"_data_lock.json")).write_text(json.dumps({"inputs":inputsha,"prediction":digest(pred),"roster":digest(R/roster),"tokenizer":digest(TOKENFILE),"protocol":digest(D/"PROTOCOL_RU.md"),"prepare":digest(__file__),"packets":digest(out),"excluded":log},indent=2),encoding="utf8")
    print(key,len(data),"different",sum(x["ranks"]["graph"]!=x["ranks"]["semlith"] for x in data))
if __name__=="__main__":main(sys.argv[1])

