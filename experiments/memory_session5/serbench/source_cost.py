"""Independent real-token audit of selected source excerpts for a Qwen reader."""
import collections,gzip,hashlib,json
from train import read,ROOT
from tokenizers import Tokenizer
from grade import read as rows
def main():
    tk=Tokenizer.from_file(str(ROOT.parent/'packets/qwen_tokenizer.json'));tk.no_padding();tk.no_truncation()
    out={}
    for split,file in [('cal500','cal_predictions.jsonl.gz'),('test500','test500_predictions.jsonl')]:
        rankings=collections.defaultdict(dict)
        for r in rows(ROOT/file):rankings[r['state_id']][r['method']]=r['ranked_evidence_ids']
        per=[]
        for row in read(split,'items'):
            cs={c['evidence_id']:c for c in row['candidate_evidence']};ranks=rankings[row['state_id']]
            for arm,rank in ranks.items():
                entries=[cs[i] for i in rank]
                texts=[str(c.get('source_path') or '')+'\n'+str(c.get('content_excerpt') or '') for c in entries]
                tokens=[len(tk.encode('\n\n'.join(texts[:k]),add_special_tokens=False).ids) for k in (5,8)]
                per.append({'state_id':row['state_id'],'method':arm,'source5':tokens[0],'source8':tokens[1]})
        out[split]={}
        for arm in sorted(set(x['method'] for x in per)):
            xs=[x for x in per if x['method']==arm];out[split][arm]={}
            for k in ('source5','source8'):
                vs=[x[k] for x in xs];out[split][arm][k]={'mean':sum(vs)/len(vs),'max':max(vs),'over6144':sum(v>6144 for v in vs)}
        with gzip.open(ROOT/(split+'_source_tokens.jsonl.gz'),'wt',encoding='utf-8') as f:
            for r in per:f.write(json.dumps(r,separators=(',',':'))+'\n')
    (ROOT/'source_cost.json').write_text(json.dumps(out,indent=2));print(out['test500'])
if __name__=='__main__':main()
