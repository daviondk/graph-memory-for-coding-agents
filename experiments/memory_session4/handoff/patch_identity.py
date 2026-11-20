"""Post-result diagnostic and artifact-identity gate. Does not alter registered decisions."""
import collections
from common import *
from grade import delta,stats
def main():
    ds=read('score_vectors.json.gz')['reader']['clean'];inp=read('clean/reader_inputs.json.gz');labels=read('labels.json.gz')
    rows=read('clean/choices.json');by={(r['issue'],r['arm'],r['reverse']):r for r in rows}
    masks=collections.defaultdict(list);records=[]
    for j,i in enumerate(ds['ids']):
        a=read('records/claude/'+i+'.json.gz')['patch'];b=read('records/gemini/'+i+'.json.gz')['patch']
        visible=inp[i]['options']['claude']['patch']==inp[i]['options']['codex']['patch']
        record={'issue':i,'same_full_patch':a==b,'same_visible_patch':visible,
                'different_grades':labels['claude|'+i]['resolved']!=labels['gemini|'+i]['resolved'],
                'source_flip':ds['gate_masks']['disagreement'][j]}
        masks['same_full_patch'].append(a==b);masks['same_visible_patch'].append(visible)
        masks['discordant_grades'].append(record['different_grades'])
        records.append(record)
    primary=ds['gate_masks']['disagreement'];actual=[v and not masks['same_full_patch'][j] for j,v in enumerate(primary)]
    values=[ds['values']['witness'][j] if v else ds['values']['empty'][j] for j,v in enumerate(actual)]
    cost=sum(by[i,'empty',rev]['usage']['total_tokens'] for i in ds['ids'] for rev in (False,True))
    marginal=sum(by[i,'witness',rev]['usage']['total_tokens'] for j,i in enumerate(ds['ids']) if actual[j] for rev in (False,True))
    pos={}
    for arm in ('empty','latest','witness'):
        r=[x for x in rows if x['arm']==arm]
        pos[arm]={'prefers_A':sum((x['choice']=='codex') if x['reverse'] else (x['choice']=='claude') for x in r),
                  'source_flips_among_distinct_full_patches':sum(ds['chosen'][arm][j][0]!=ds['chosen'][arm][j][1] for j in range(len(ds['ids'])) if not masks['same_full_patch'][j])}
    sub={}
    for name,mask in masks.items():
        inds=[j for j,v in enumerate(mask) if v];groups=[ds['groups'][j] for j in inds]
        sub[name]={'n':len(inds),'metrics':{arm:stats([ds['values'][arm][j] for j in inds]) for arm in ('empty','latest','witness','heldout_repository_prior')}}
    result={'counts':{k:sum(v) for k,v in masks.items()},'position_diagnostics':pos,'subgroups':sub,
            'post_result_artifact_gate':{'gated_issues':sum(actual),'success':stats(values),'incremental_tokens':marginal,'total_tokens':cost+marginal,
                                        'versus_registered_gate':delta(values,ds['values']['gate_disagreement'],ds['groups']),
                                        'versus_never_read':delta(values,ds['values']['empty'],ds['groups'])},
            'full_patch_equal_but_grade_diff':sum(r['same_full_patch'] and r['different_grades'] for r in records)}
    write('patch_identity_results.json',result);write('patch_identity_rows.json',records);print(canon(result))
if __name__=='__main__':main()
