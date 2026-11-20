"""Only pre-rerun fields enter the forecast inputs. Each future observation is separate."""
from pathlib import Path
from collections import Counter
import gzip,json,hashlib
from bson_stream import docs
P=Path(__file__).resolve().parent
def line(x):return json.dumps(x,separators=(',',':'),sort_keys=True,ensure_ascii=True)
def load_reasons():
    result={};n=0
    with gzip.open(P/'restarted_logs.prefix.gz.part','rb') as f:
        try:
            for d in docs(f):
                info=(d.get('analysis') or {}).get('original') or {}
                reasons=info.get('reasons')
                if not isinstance(reasons,list):continue
                n+=1
                sig=set()
                for reason in reasons:
                    if isinstance(reason,dict):
                        value=reason.get('category') or reason.get('type') or 'unspecified'
                    else:value='unspecified'
                    sig.add(value.lower().strip()[:64] if isinstance(value,str) else 'unspecified')
                key=d['id']
                if key in result and result[key]!=sorted(sig):result[key]=None
                elif key not in result:result[key]=sorted(sig)
        except EOFError:pass # expected cutoff at frozen compressed prefix
    return result,n
def project(kind,reason=None):
    reasons=reason or {}; counts=Counter();raw={};duplicates=set()
    with gzip.open(P/('restarted_'+kind+'.bson.gz'),'rb') as f:
        for doc in docs(f):
            counts['source_records']+=1
            i=doc['id']
            if i in raw:duplicates.add(i);continue
            a=doc['old'];b=doc['new']
            raw[i]=(a,b)
    counts['distinct_ids']=len(raw); counts['duplicate_ids_excluded']=len(duplicates)
    obs={};future={}
    for i,(a,b) in raw.items():
        if i in duplicates:continue
        if any(a.get(k)!=b.get(k) or a.get(k) is None for k in ['id','repository_id','commit_id']) or a['id']!=i:counts['mismatched_identity']+=1;continue
        if kind=='jobs' and (i not in reasons or reasons[i] is None):counts['no_eligible_prefix_analysis']+=1;continue
        if a['state'] not in ('failed','errored'):counts['other_first_state']+=1;continue
        if b['state'] not in ('passed','failed','errored'):counts['other_second_state']+=1;continue
        times=[a.get('started_at'),a.get('finished_at'),b.get('started_at'),b.get('finished_at')]
        if any(not isinstance(x,int) or x<=0 for x in times) or times!=sorted(times):counts['missing_or_nonsequential_timestamps']+=1;continue
        jobs=len(a.get('job_ids') or [])
        bucket='1' if jobs==1 else '2-4' if 2<=jobs<=4 else '5+' if jobs else 'unknown'
        mode={'id':i,'repo':a['repository_id'],'commit':a['commit_id'],'status':a['state'],'event':a.get('event_type') or 'unknown',
              'language':a.get('language') or 'unknown','matrix':bucket,'decision_at':times[1]}
        if kind=='jobs':mode['reasons']=reasons[i]
        obs[i]=mode
        future[i]={'id':i,'available_after':times[3],'duration_s':(times[3]-times[2])/1000,'passed':int(b['state']=='passed')}
    counts['eligible']=len(obs)
    def gz(path,data):
        with (P/path).open('wb') as fp:
            with gzip.GzipFile(fileobj=fp,mode='wb',mtime=0) as out:
                for key in sorted(data):out.write((line(data[key])+'\n').encode())
    gz(kind+'_inputs.jsonl.gz',obs);gz(kind+'_labels.jsonl.gz',future)
    return counts
if __name__=='__main__':
    b=project('builds'); r,n=load_reasons();j=project('jobs',r);j['prefix_records_with_analysis']=n
    (P/'cohorts.json').write_text(json.dumps({'builds':b,'jobs':j},indent=2));print('input projections sealed')
