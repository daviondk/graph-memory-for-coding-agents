from collections import Counter
from trace import ROOT,Tokenizer,writes
from train import read,lines
from dense_prepare import PFX
from features import digest
def main():
    t=Tokenizer.from_file(str(ROOT/'weights/tokenizer.json'));t.no_truncation();t.no_padding()
    get=lambda s:t.encode(s,add_special_tokens=False).ids
    rows=[]
    for row in read('cal500','items'):
        current='\n'.join([row.get('information_need') or '',row.get('current_subgoal') or '',row.get('issue') or ''])
        rows.append((row['state_id'],row['repo'],row['instance_id'],row['state_type'],get(PFX+current)[:252],writes(row)))
    output=[]
    for sid,repo,issue,typ,base,own in rows:
        candidates=[r for r in rows if r[1]!=repo and r[2]!=issue and r[3]==typ]
        closest=min(candidates,key=lambda r:(abs(r[5]['addresses'][1]-own['addresses'][1]),digest('dense-foreign|'+sid+'|'+r[0])))
        group={k:own[k][0] for k in ('addresses','tail','arguments','empty')};group['foreign']=closest[5]['addresses'][0]
        enc={k:[t.token_to_id('[CLS]')]+base+[t.token_to_id('[SEP]')]+get(v)[:255]+[t.token_to_id('[SEP]')] for k,v in group.items()}
        assert max(map(len,enc.values()))<=510
        output.append({'state_id':sid,'foreign_state':closest[0],'foreign_note_qwen':closest[5]['addresses'][1],'own_note_qwen':own['addresses'][1],'q_first':len(base),'ids':enc})
    lines(ROOT/'fixed_queries.jsonl.gz',output)
if __name__=='__main__':main()
