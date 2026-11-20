"""Supplementary deployable prefix-at-6144 control. Preserve original item-only rankings."""
from pathlib import Path
import hashlib,json,sys
from train import read,lines,ROOT
from grade import read as loadrows,score_predictions,validate_predictions
from tokenizers import Tokenizer
def main():
    tk=Tokenizer.from_file(str(ROOT.parent/'packets/qwen_tokenizer.json'));tk.no_padding();tk.no_truncation()
    out={}
    for split,file in [('cal500','cal_predictions.jsonl.gz'),('test500','test500_predictions.jsonl')]:
        pred=loadrows(ROOT/file);lookup={r['state_id']:r for r in pred if r['method']=='pair_completion'}
        rs=[];counts=[]
        for row in read(split,'items'):
            sid=row['state_id'];r=lookup[sid];docs={c['evidence_id']:str(c.get('source_path') or '')+'\n'+str(c.get('content_excerpt') or '') for c in row['candidate_evidence']}
            ids=[];sent='';used=0
            for k in r['ranked_evidence_ids']:
                proposed=sent+'\n\n'+docs[k] if ids else docs[k]
                tokens=len(tk.encode(proposed,add_special_tokens=False).ids)
                if tokens>6144:break
                ids.append(k);used=tokens;sent=proposed
            rs.append({'method':'pair_completion_cap6144','state_id':sid,'ranked_evidence_ids':ids})
            counts.append((used,len(ids)))
        project=loadrows(ROOT/('cal_candidates.jsonl.gz' if split=='cal500' else 'test_candidates.jsonl.gz'))
        validate_predictions(rs,project)
        fn=ROOT/(split+'_cap6144.jsonl');lines(fn,rs)
        info={'sha256':hashlib.sha256(fn.read_bytes()).hexdigest(),'rows':len(rs),'changed':sum(len(r['ranked_evidence_ids'])!=len(lookup[r['state_id']]['ranked_evidence_ids']) for r in rs),'mean_source_tokens':sum(q for q,_ in counts)/len(rs),'max_source_tokens':max(q for q,_ in counts)}
        if split=='cal500':info['official_metrics']=score_predictions(rs,list(read(split,'labels')),[5,8],dataset=project)[1]
        out[split]=info
    (ROOT/'cap_results.json').write_text(json.dumps(out,indent=2));print({k:(v['changed'],v['max_source_tokens']) for k,v in out.items()})
if __name__=='__main__':main()
