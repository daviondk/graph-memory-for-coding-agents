"""Describe vendor index omissions without displaying candidate source or any sensitive text."""
import re
from pathlib import Path
from grade import stats
from run import D,load,readgz,save

def main():
    items={(x['panel'],x['idx']):x for x in readgz(D/'paired.jsonl.gz') if x['stage']=='fresh'}
    out={};filtered=[];total_ref=0;gold_ref=0;gold_empty=0
    for tag in ['python_cff','python_cfr']:
        folder=D/'native'/tag
        refused={(int(i),int(j)) for i,j in re.findall(r'^refused: .*?corpus[\\/]i(\d+)[\\/]c(\d+)\.py',
            (folder/'index.log').read_text('utf8',errors='replace'),flags=re.M)}
        omitted_gold=0;empties=set();ret=[];ok=[]
        for pos,(panel,i,repo,returned,rank) in enumerate(readgz(D/('native_'+tag+'.jsonl.gz'))):
            row=items[panel,i];assert row['project']==repo
            d=folder/'corpus'/f'i{pos:05d}'
            empty={j for j in range(row['n']) if not (d/f'c{j:03d}.py').read_text(encoding='utf8').strip()}
            empties.update((pos,j) for j in empty)
            if (pos,row['gold']) in refused:omitted_gold+=1
            if row['gold'] in empty:gold_empty+=1
            if not empty and not any(pos==n for n,j in refused):ok.append(row)
            ret.append(returned/row['n'])
        filtered.extend(ok);total_ref+=len(refused);gold_ref+=omitted_gold
        out[tag]=dict(refused=len(refused),refused_gold=omitted_gold,empty_or_whitespace=len(empties),kept=len(ok),
            mean_fraction_returned=sum(ret)/len(ret))
    save('native_sensitivity.json',dict(by_config=out,refused=total_ref,refused_gold=gold_ref,blank_gold=gold_empty,
         no_blank_and_no_flag=stats(filtered)))
if __name__=='__main__':main()
