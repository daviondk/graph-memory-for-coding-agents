"""Emit checked forecasts for every eligible prefix and re-run each writer with the entire suffix cut away."""
import time
from frontier import *

def external():
    members={d['rfilename']:d for d in read(prefix.V/'memory-stage-fetch'/'source-manifest.json')['siblings']}
    out=[];checked=collections.Counter()
    for repo in ('elastic/curator','apiflask/apiflask'):
        dire=prefix.V/'benchmark/history/python'/repo.replace('/','__')
        for file in sorted(dire.glob('*/*.traj.json')):
            k=file.relative_to(prefix.V/'benchmark').as_posix();b=file.read_bytes();digest=h(b);m=members[k];up=m.get('lfs',{}).get('sha256') or m['blobId']
            assert up==(digest if len(up)==64 else hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest())
            issue=next(m['content'] for m in json.loads(b)['messages'] if m['role']=='user').partition('</pr_description>')[0]
            checked['total']+=1
            if prefix.ext.BAD.search(issue) or FORBID.search(issue):checked['excluded']+=1;continue
            out.append(dict(iid=file.parent.name,repo=repo,file=k,sha=digest,upstream=up))
    return out,checked

def replay(msgs,rows,repo):
    end={r['index']:r for r in rows};first=rows[0];st=State(first['issue'],repo);ans={}
    for idx,mi,cid,cmd,tool in prefix.calls(msgs):
        if idx in end:
            r=end[idx]; assert r['id'].endswith('|'+cid) and r['message']==mi
            ans[r['id']]=st.snap(r['key']['root'],r['docs'])
        st.update(idx,cid,cmd,tool)
        if idx>=max(end):break
    assert len(ans)==len(rows)
    return ans

def main():
    x0=time.perf_counter()
    ground=read(G/'cases.gz')
    gset={r['id'] for r in ground}
    ext,flow=external()
    rosters={'primary':read(R/'roster.json'),'replication':read(R/'replication/roster.json'),
             'grounded_all':read(G/'roster.json'),'external':ext}
    used=set();sels={};evals={};proof={};flows={};refs={}
    for n,rs in rosters.items():
        known={}
        if n in ('primary','replication'):
            folder=R if n=='primary' else R/'replication'
            assert h((folder/'inputs.json.gz').read_bytes())==read(folder/'forecast.lock.json')['files']['inputs.json.gz']
            for q in read(folder/'inputs.json.gz'):known.setdefault(q['iid'],[]).append(q)
        assert not used&{r['repo'] for r in rs}
        used|={r['repo'] for r in rs};ii=[];pp=[];vv=[]
        for rec in rs:
            if known and rec['iid'] not in known:continue
            rows=known.get(rec['iid'],[]) if known else list(prefix.sample(rec))
            if not rows:continue
            raw=(prefix.V/'benchmark'/rec['file']).read_bytes();assert h(raw)==rec['sha']
            msgs=json.loads(raw)['messages']
            ans=replay(msgs,rows,rec['repo'])
            for q in rows:
                cid=q['id'];s=ans[cid]
                clipped=msgs[:q['message']+1]
                check=replay(clipped,[q],rec['repo'])[cid]
                assert compact(check)==compact(s)
                row={'id':cid,'iid':q['iid'],'repo':q['repo'],'index':q['index'],'message':q['message'],'issue':q['issue'],'key':q['key'],'viewed':q['docs'],
                     'frontier':s['front'],'opened_count':len(s['opened']),'opened_bytes':len(compact(s['opened'])),
                     'frontier_bytes':len(compact(s['front'])),'grounded_member':cid in gset}
                t=time.perf_counter_ns()
                ranks,scores=predict(q,s)
                pp.append(dict(id=cid,iid=q['iid'],repo=q['repo'],ranks=ranks,scores=scores))
                ii.append(row);vv.append(dict(id=cid,message=q['message'],cut_messages=len(clipped),prefix_sha=h(compact(clipped)),
                    state_sha=h(compact(s)),input_sha=h(compact(row)),ranking_ns=time.perf_counter_ns()-t))
        assert len(ii)==len({r['id'] for r in ii})
        flows[n]={'roster':len(rs),'anchors':len(ii),'anchor_tasks':len({r['iid'] for r in ii}),'repos':sorted({r['repo'] for r in rs}),
                  'old_slots':sum(len(r['viewed']) for r in ii),'frontier_slots':sum(len(r['frontier']) for r in ii),
                  'anchor_nonempty_frontier':sum(bool(r['frontier']) for r in ii),'grounded_original':sum(r['grounded_member'] for r in ii)}
        sels[n]=ii;evals[n]=pp;proof[n]=vv
        print(n,flows[n],flush=True)
    assert [flows[k]['anchors'] for k in ('primary','replication','grounded_all')]==[267,73,111]
    assert sum(r['grounded_member'] for v in sels.values() for r in v)==len(gset)
    save('rosters.json.gz',rosters);save('frontier_inputs.json.gz',sels);save('forecasts.json.gz',evals);save('causal_receipts.json.gz',proof)
    deps=[R/'prefix.py',R/'rank.py',prefix.R12/'extract.py',R/'inputs.json.gz',R/'replication/inputs.json.gz',G/'cases.gz',G/'roster.json']
    save('flow.json',{'panels':flows,'external_source':flow,'build_sec_including_invariance':time.perf_counter()-x0,'sources':{str(p):h(p.read_bytes()) for p in deps}})
    names=['PROTOCOL_RU.md','frontier.py','freeze.py','rosters.json.gz','frontier_inputs.json.gz','forecasts.json.gz','causal_receipts.json.gz','flow.json']
    save('forecast.lock.json',{n:h((D/n).read_bytes()) for n in names})
if __name__=='__main__':main()
