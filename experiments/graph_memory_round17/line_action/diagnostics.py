"""Report where the saved candidates and selected actions constrained the paired contrast."""
import collections
import json
from statistics import median
from study import ROOT, ARMS, read, put
def main():
    scored=read(ROOT/'evaluation.json.gz');calls=[json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines()]
    summaries={}
    for arm in ARMS:
        total=collections.Counter();lengths=[];examples=[]
        k='qwen/'+arm;l='lexical/'+arm
        for r in scored:
            a,b=r['outcomes'][k],r['outcomes'][l]
            total['cases']+=1
            total['same_choice']+=a['choice']==b['choice']
            total['menu_hit_and_no_choice_hit']+=a['patch_menu_hit'] and not a['patch_read_hit']
            total['precision_one_without_patch']+=a['precision']==1 and not a['patch_read_hit']
            total['precision_one']+=a['precision']==1
            if a['available']:lengths.append(a['read_lines'])
            if a['patch_read_hit']!=b['patch_read_hit']:examples.append(dict(id=r['id'],qwen=a['choice'],lexical=b['choice'],qwen_hits=a['patch_read_hit'],lexical_hits=b['patch_read_hit']))
        summaries[arm]={'counts':total,'median_read_lines_valid':median(lengths) if lengths else None,'actual_lengths':dict(collections.Counter(lengths)),'examples':examples}
    qwen_diff=[]
    for r in scored:
        a,b=r['outcomes']['qwen/scope24'],r['outcomes']['qwen/lexical24']
        if a['choice']!=b['choice']:
            qwen_diff.append({'id':r['id'],'scope24':a['choice'],'lexical24':b['choice'],'scope_patch':a['patch_read_hit'],'lexical_patch':b['patch_read_hit']})
    bad=[]
    for r in calls:
        if not r['valid']:
            obj=json.loads(r['raw'])['choices'][0]['message']
            bad.append({'sha':r['sha'],'tool_calls':obj.get('tool_calls') or []})
    put('diagnostics.json',{'arms':summaries,'scope_lexical_changed':qwen_diff,'invalid_native':bad})
    from evaluate import discordant
    supplemental={solver:{metric:discordant(scored,solver+"/lexical24",solver+"/recent",metric) for metric in ("patch_read_hit","patch_menu_hit")} for solver in ("qwen","lexical")}
    put("additional_contrast.json",{"timing":"descriptive analysis after primary outcomes","lexical24_vs_recent":supplemental})
    print({k:v['counts'] for k,v in summaries.items()},'changed',len(qwen_diff),'invalid',len(bad))
if __name__=='__main__': main()
