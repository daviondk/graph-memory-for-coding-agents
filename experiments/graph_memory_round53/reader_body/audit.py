"""Independently reconstruct every counterfactual prompt with the same model's native tokenizer."""
from experiment import *

def main():
    input_seal=get("input-seal.json");answer_seal=get("answer-seal.json");grade=get("grade-seal.json")
    files=[(input_seal,"contexts","contexts.json.gz"),(input_seal,"prompts","prompts.json.gz"),
           (input_seal,"donors","donors.json.gz"),(answer_seal,"input","input-seal.json"),(answer_seal,"answers","answers.json.gz"),
           (grade,"results","results.json"),(grade,"records","records.json.gz"),(grade,"answers","answer-seal.json")]
    for receipt,field,name in files:assert receipt[field]==sha(D/name)
    choices=get("contexts.json.gz");prompts=get("prompts.json.gz");answers=get("answers.json.gz")
    original=read(PREV/"contexts.json.gz");prior=read(PREV/"prompts.json.gz");raw=read(ORIGINAL)
    assert set(answers)==set(prompts) and all(key(v)==h for h,v in prompts.items())
    forbidden=disallowed(set(choices));other=read(PREV.parent/"selection.json.gz")
    docs=raw["second"];rows={i for c in choices.values() for i,_,_ in c["refs"].values()}
    assert {c["donor"] for c in choices.values()}.issubset(rows)
    common.RUN=D
    clipped_text=0;clipped_separator=0
    with server(READER,["--parallel","1","--ctx-size","1024","--flash-attn","on","--threads","4"],"audit-tokenizer",18953) as (url,s,hw):
        assert hw["build"]==input_seal["hardware"]["build"]
        def tokens(t,special=False):
            r=s.post(url+"/tokenize",json=dict(content=t,parse_special=special,add_special=False),timeout=30);r.raise_for_status();return r.json()["tokens"]
        tail=tokens("<|im_end|>\n<|im_start|>assistant\n",True)
        independent={i:(tokens(docs[str(i)][0]),tokens(docs[str(i)][0]+"\n"),tokens(docs[str(i)][1])[:192]) for i in rows}
        for q,c in choices.items():
            original_row=original["fallback|"+q];w=c["second_tokens"];donor=c["donor"]
            blacklist=set(other[q]["second"].values())|{c["first"]}|{v[0] for v in c["refs"].values()}
            excluded_titles=forbidden[q]|{canon(raw["first"][str(c["first"])][0])}|{canon(docs[str(v[0])][0]) for v in c["refs"].values()}
            needed=max(w-n for n in c["header"].values())
            eligible={i for i in rows if i not in blacklist and canon(docs[str(i)][0]) not in excluded_titles and len(independent[i][2])>=needed}
            rank=lambda i:hashlib.sha256(("r53-donor-v1|"+q+"|"+str(i)).encode()).hexdigest()
            assert donor==min(eligible,key=rank)
            for a in ARMS:
                i,k,n=c["refs"][a];oid,ok,length=original_row["refs"][a]
                assert oid==i and n==length
                t,head,_=independent[i]
                clipped_text+=w<len(t)
                clipped_separator+=len(t)<=w<len(head)
                head=head[:w];assert len(head)==c["header"][a]
                before=prior[ok];end=len(before)-len(tail);start=end-w
                assert before[start:start+len(head)]==head and before[end:]==tail
                actual=before[:start]+head+independent[donor][2][:w-len(head)]+tail
                assert actual==prompts[k] and len(actual)==n
    r=get("results.json")
    assert r["discordant"]==sum(c["refs"][ARMS[0]][0]!=c["refs"][ARMS[1]][0] for c in choices.values())
    out=dict(paired=len(choices),checked_assignments=2*len(choices),unique=len(answers),distinct_donors=r["distinct_donors"],
        title_content_clipped=clipped_text,only_separator_clipped=clipped_separator,actual_width_differences=sum(c["header"][ARMS[0]]!=c["header"][ARMS[1]] for c in choices.values()),
        token_equal=True,code=sha(Path(__file__)))
    put("audit.json",out);print(out)
if __name__=="__main__":main()
