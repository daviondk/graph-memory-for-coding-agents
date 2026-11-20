import collections,json,re,subprocess,sys
from harvest import D,get,save,sha
from git_pairs import ENV,git,local
from replay import tree_names,allowed,normal_pat
def enc(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(",",":")).encode()
def verify_query(r,rev):
    # Independent oracle using Git blob bytes directly, no git grep or unified-diff evaluation.
    k=r["key"];repo=r["repo"];root=local(repo);names=tree_names(repo,rev)
    if k["kind"]=="path":
        cp=git(root,"cat-file","-e",rev+":"+k["literal"],check=False)
        return True,cp.returncode==0,0
    ps=sorted(p for p in names if allowed(p,k));exists=any(p==k["scope"] or p.startswith(k["scope"]+"/") or k["scope"]=="." for p in names)
    if not exists:return False,None,0
    if k["kind"]=="name":
        from pathlib import PurePosixPath
        hits={p for p in ps if PurePosixPath(p).name==k["literal"]}
        if not k["regular_only"]:hits.update(str(f) for p in ps for f in PurePosixPath(p).parents if f.name==k["literal"])
        return True,bool(hits),0
    proc=subprocess.run(["git","-C",str(root),"cat-file","--batch"],input=b"".join((rev+":"+p+"\n").encode() for p in ps),capture_output=True,env=ENV,check=True,timeout=60)
    data=proc.stdout; at=0;total=0;possible=False
    for p in ps:
        ix=data.index(b"\n",at);h=data[at:ix].split();assert h[1]==b"blob"
        size=int(h[2]);payload=data[ix+1:ix+1+size];at=ix+2+size;total+=size
        if b"\0" not in payload[:8000] and normal_pat(k).search(payload):possible=True
    assert at==len(data)
    return True,possible,total
def compute():
    locked=get(D/"pre_oracle.lock.json");assert all(sha((D/f).read_bytes())==h for f,h in locked['files'].items())
    src=get(D/'keys.json');pop=get(D/'roster.json');notes=get(D/'action_notes.json');rec=get(D/'oracle.json');recover=get(D/'recovery.json')
    used={ (r['iid'],r['step']):r for r in src};rows=[]
    for r in rec:
        oracles=[]
        for rev,oracle in [(r['old_sha'],r['old_oracle']),(r['new_sha'],r['new_oracle'])]:
            valid,hit,b=verify_query(r,rev)
            assert (valid,hit)==(oracle['valid'],oracle.get('hit')),(r['iid'],r['step'],rev)
            oracles.append((valid,hit,b))
        rows.append({**r,'old_scan_bytes':oracles[0][2],'new_scan_bytes':oracles[1][2],'future_mention':used[r['iid'],r['step']]['future_mention'],'future_exact_args':used[r['iid'],r['step']]['future_exact_args']})
    save(D/'checked_rows.json',rows)
    by_tier={}
    for tier in ('strict','weak'):
        group=[r for r in rows if r['tier']==tier];valid=[r for r in group if r['old_oracle'].get('hit') is False and r['new_oracle']['valid']]
        policies={'retain_all_stale':(lambda r:True,lambda r:False),'all_rerun':(lambda r:True,lambda r:r['changed_repo']),'scope':(lambda r:True,lambda r:r['scope']),'exact':(lambda r:True,lambda r:r['exact']),'use':(lambda r:r['use_next_three'],lambda r:r['exact']),'hash':(lambda r:r['hash_keep'],lambda r:r['exact']),'no_memory':(lambda r:False,lambda r:False)}
        scores={}
        for m,(keep,probe) in policies.items():
            reread=[r for r in valid if not keep(r) or probe(r)]
            stale=[r for r in valid if keep(r) and not probe(r) and r['new_oracle']['hit']]
            extra=[r for r in reread if not r['new_oracle']['hit']]
            # Per-write counts including only serialized entries, excludes the policy dispatcher.
            scores[m]={'stored_valid':sum(keep(r) for r in valid),'stored_original':sum(keep(r) for r in group),'bytes_valid':sum(len(enc(r['key'])) for r in valid if keep(r)),'reread':len(reread),'stale':len(stale),'extra':len(extra),'diff_bytes_examined':sum(r['diff_bytes'] for r in valid if keep(r) and m in ('exact','hash','use')),'cold_cache_rereads':sum(not keep(r) for r in valid),'full_blob_payload_bytes_of_rereads':sum(r['new_scan_bytes'] for r in reread)}
        # All projections are over raw *authors' tool inputs*, without assistant thoughts.
        by_tier[tier]={'raw_events':sum(r['tier']==tier for r in notes),'n_all':len(group),'n_valid':len(valid),'tasks':len({r['iid'] for r in valid}),'repos':len({r['repo'] for r in valid}),'changed':sum(r['new_oracle']['hit'] for r in valid),'excluded':[{'iid':r['iid'],'key':r['key'],'reason':r['old_oracle'].get('reason')} for r in group if r not in valid],'panels':dict(collections.Counter(r['panel'] for r in valid)),'mention_after_three':sum(r['future_mention'] for r in valid),'repeat_same_args_after_three':sum(r['future_exact_args'] for r in valid),'meant_next_three':sum(r['use_next_three'] for r in valid),'used_changed':sum(r['use_next_three'] and r['new_oracle']['hit'] for r in valid),'hash_changed':sum(r['hash_keep'] and r['new_oracle']['hit'] for r in valid),'scores':scores}
    origin=[r for r in rows if r['new_oracle'].get('hit') and r['old_oracle'].get('hit') is False]
    numbers={'population':len(pop),'actions':sum(r['projected_actions'] for r in pop),'pair_count':len(set(r['iid'] for r in rows)),'pair_direct_parent':len(set(r['iid'] for r in rows if r['parent_match'])),'queries':len(rows),'oracle_checks':2*len(rows),'changed_parent':[(r['iid'],r['parent_match']) for r in origin],'panels':by_tier,'targets':len([r for r in recover if r['target']]),'recovery_scores':{k:{'issued':sum(bool(r[k]) for r in recover),'correct':sum(bool(r['target'] and r[k]==r['target']) for r in recover)} for k in ('wrong','convention','suffix','stored_candidate','convention_then_suffix')}}
    save(D/'summary.json',numbers);print(json.dumps(numbers,ensure_ascii=True))
if __name__=='__main__':compute()
