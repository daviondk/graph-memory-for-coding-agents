from util import *
def main():
    up=BASE/'upstream';source={}
    expected={'oracle':('raw',False),'naive':('raw',True),'alert':('system_alert',True),'diff':('git',True),'block_context':('block_context',True)}
    for p in sorted((up/'bench/runs').glob('*_eval_traced.json')):
        a=read(p);label=p.name.split('hotpot40_')[-1].split('_eval_traced')[0]
        cli,mut=expected[label]
        assert a['policy']==cli and a['apply_a_side_mutations']==mut
        assert (a['race_candidate_path'] is not None)==mut and len(a['tasks'])==40
        tmp={k:a[k] for k in ('policy','max_events','opaque_doc_ids','max_grep_per_event','max_tool_calls_per_event','race_delay_steps','apply_a_side_mutations','model','max_workers')}
        tmp['race_candidate_present']=a['race_candidate_path'] is not None
        tmp['sha256']=digest(p.read_bytes());source[p.name]=tmp
    assert len(source)==15
    content={p.name:digest(p.read_bytes()) for p in sorted((up/'bench/data/hotpotqa/fullwiki/validation').glob('*')) if p.is_file()}
    save(ROOT/'published_settings.json',{'archives':source,'hotpot_arrow_inputs':content})
    print('verified objective CLI/race mapping across',len(source),'author-run archives')
if __name__=='__main__':main()

