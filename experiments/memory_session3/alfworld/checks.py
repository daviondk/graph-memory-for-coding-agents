"""Independent audit. --native reproduces 39 scout trajectories in the experiment's native TextWorld container.
--final requires all 3 closed-loop expansions. Default reports only complete files physically present.
"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,csv,gzip,hashlib,json,re
import ast
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads((ROOT/p).read_bytes())
def digest(data):return hashlib.sha256(data).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(',',':'))
def load_traces(d):
    for path in sorted((ROOT/d).glob('*.json.gz')):
        group=json.loads(gzip.decompress(path.read_bytes()))
        ep=group[0]['episode']
        assert path.name==digest(ep.encode())[:20]+'.json.gz'
        assert not any(x['episode']!=ep for x in group)
        yield from group
def public_items(commands,place):
    out=set()
    for cmd in commands:
        a=re.fullmatch(r'take (.+) (\d+) from (.+)',cmd)
        if a and a[3]==place:out.add(a[1])
        a=re.fullmatch(r'use (.+) (\d+)',cmd)
        if a:out.add(a[1])
    return sorted(out)
def scout_samples(r,extra=None):
    cells={};place=''
    for cmds,cmd in [(s['available'],s['command']) for s in r['steps']]+([(extra,None)] if extra is not None and len(r['steps'])<50 else []):
        if place and ('open '+place) not in cmds and place not in cells:
            cells[place]=public_items(cmds,place)
        if cmd and cmd.startswith('go to '):place=cmd[6:]
    return cells
def train_replay():
    from engine import DATA,create
    import textworld
    states=[]
    for r in load_traces('train_logs'):
        env=create(DATA/r['episode']);s=env.reset()
        assert r['initial']==s.feedback
        for step in r['steps']:
            observed=sorted(s.admissible_commands)
            assert observed==step['available'] and step['command'] in observed
            s,reward,done=env.step(step['command'])
            assert (s.feedback,int(reward),bool(done),bool(s.won))==(step['feedback'],step['reward'],step['done'],step['won'])
        final=sorted(s.admissible_commands)
        original=dict(r['samples'])
        assert scout_samples(r,final)==original
        assert list(original)==list(scout_samples(r,final))
        states.append({'episode':r['episode'],'final_feedback':s.feedback,'final_admissible':final,'steps':len(r['steps']),'samples':len(original),'earlier_missing':len(original)-len(scout_samples(r))})
        env.close()
    assert len(states)==39
    with gzip.open(ROOT/'audit_native_final.json.gz','wt',encoding='utf8') as f:json.dump(states,f)
    print(json.dumps({'textworld_version':textworld.__version__,'train':len(states),'verified_steps':sum(x['steps'] for x in states),'verified_samples':sum(x['samples'] for x in states),'recovered':sum(x['earlier_missing'] for x in states)},indent=1))

def eval_replay():
    """Independently repeat environment evaluation on one salted, outcome-blind selection per family/floor."""
    from engine import DATA,create
    roster=read('roster.json')['valid_unseen']
    chosen=set()
    for field in ['family','floorplan']:
        for name in sorted({r[field] for r in roster}):
            candidates=[r['episode'] for r in roster if r[field]==name]
            chosen.add(min(candidates,key=lambda ep:digest(('audit-only-replay|'+ep).encode())))
    records=[]
    for folder in ['traces','planner_traces']:
        for ep in sorted(chosen):
            path=ROOT/folder/(digest(ep.encode())[:20]+'.json.gz')
            rows=json.loads(gzip.decompress(path.read_bytes()))
            env=create(DATA/ep)
            for r in rows:
                s=env.reset();assert r['initial']==s.feedback
                for step in r['steps']:
                    assert sorted(s.admissible_commands)==step['available']
                    s,reward,done=env.step(step['command'])
                    assert (s.feedback,int(reward),bool(done),bool(s.won))==(step['feedback'],step['reward'],step['done'],step['won'])
                records.append({'episode':ep,'arm':r['arm'],'steps':len(r['steps']),'won':bool(s.won)})
            env.close()
    assert len(records)==10*len(chosen)
    (ROOT/'audit_native_evaluation.json').write_text(json.dumps(records,indent=1),encoding='utf8')
    print('independently re-executed native eval',len(chosen),'games',len(records),'rollouts',sum(r['steps'] for r in records),'commands')

def verify_plans():
    if not (ROOT/'planner_lock.json').exists():return {}
    prior=read('learned.json');plans=read('plans.json');counts=Counter();absent=Counter();invalid=Counter();models=set();costs=Counter()
    ep_init=read('initial.json')
    from policy import goals
    expected=set()
    for x in ep_init:
        obj,dst,op,_=goals(x['observation'])
        assert obj
        classes=sorted({c[6:].rsplit(' ',1)[0] for c in x['commands'] if c.startswith('go to ')})
        for t in ([obj,dst] if op=='light' else [obj]):
            for name in ['q_prior','q_shown','q_placebo']:expected.add(canon([t,classes,name]))
    assert set(plans)==expected
    file_set=set()
    for serialized,rec in plans.items():
        t,locations,arm=json.loads(serialized)
        source=rec['evidence_source'];rank=rec['rank']
        assert set(rank)==set(locations) and len(rank)==len(locations)
        c=read('planner_calls/'+rec['key']+'.json');file_set.add(rec['key'])
        rq=c['request'];rsp=c['response']
        assert digest(canon(rq).encode())==rec['key'] and rsp['model']==rq['model']
        assert len(rq['messages'])==2 and rq['temperature']==0 and rq['max_tokens']==256
        text='Target: '+t+'\nAllowed locations: '+', '.join(locations)
        if arm=='q_prior':assert source is None
        elif arm=='q_shown':assert source==t
        else:
            donors=sorted(k for k in prior['hits'] if k!=t)
            assert source==donors[int(digest(('unrelated|'+t).encode()),16)%len(donors)] and source!=t
        if source is not None:
            text+='\nPrior household search observations for this target (location: present / examined):\n'+'\n'.join(f"{c}: {prior['hits'].get(source,{}).get(c,0)} / {prior['seen'].get(c,0)}" for c in locations)
        assert text==rq['messages'][1]['content']
        raw=rsp['choices'][0]['message']['content']
        recovered=list(dict.fromkeys(v for v in re.findall('[a-z]+',raw.lower()) if v in locations))
        assert rank==recovered+[c for c in locations if c not in recovered]
        absent[arm]+=int(len(recovered)!=len(locations))
        try:literal=json.loads(raw)
        except ValueError:literal=None
        invalid[arm]+=int(not isinstance(literal,list) or literal!=rank)
        counts[arm]+=1
    assert file_set=={p.stem for p in (ROOT/'planner_calls').glob('*.json')}
    local_events=ROOT.parents[3]/'x20-3-27b-runtime'/'requests.jsonl'
    refs=read('audit_planner_origin.json') if (ROOT/'audit_planner_origin.json').exists() else []
    if local_events.exists():
        ids={read('planner_calls/'+k+'.json')['response']['id'] for k in file_set}
        fields=['id','message_sha256','payload_sha256','http_status','chat_template_thinking','seed','max_output','temperature','top_p','top_k','min_p','repeat_penalty','usage','reason_chars']
        with local_events.open(encoding='utf8') as stream:
            origin=[{k:r[k] for k in fields} for ln in stream if (r:=json.loads(ln)).get('id') in ids]
        assert len(origin)==len(ids)
        if refs:assert origin==refs
        else:(ROOT/'audit_planner_origin.json').write_text(json.dumps(origin,indent=1),encoding='utf8')
        refs=origin
    events={r['id']:r for r in refs}
    for k in file_set:
        cache=read('planner_calls/'+k+'.json');out=cache['response'];u=out['usage'];assert u['completion_tokens']<=256
        if events:
            req=cache['request'];e=events[out['id']]
            assert e['http_status']==200 and e['seed']==17112026 and e['max_output']==256 and e['temperature']==0
            assert e['reason_chars']==0 and e['chat_template_thinking'] is False and e['usage']==u
            assert digest(json.dumps(req['messages'],ensure_ascii=False,sort_keys=True).encode())==e['message_sha256']
            native=dict(req)
            native.update(cache_prompt=False,temperature=0.0,top_p=.95,top_k=20,min_p=0.,repeat_penalty=1.)
            native['chat_template_kwargs']={'enable_thinking':False}
            assert digest(json.dumps(native,ensure_ascii=False).encode())==e['payload_sha256']
        models.add((out['model'],out.get('system_fingerprint')))
        for key in ('prompt_tokens','completion_tokens'):costs[key]+=u[key]
    return {'assignments':counts,'calls':len(file_set),'matched_native_origin':len(events),'selective_regex_fallback':absent,'not_requested_json':invalid,'models':[list(x) for x in models],'usage':costs}
def audit(full):
    roster=read('roster.json');tr=roster['train'];un=roster['valid_unseen'];se=read('transfer_seen.json')
    manifest={}
    if full and (ROOT/'audit_archive_sha256.json').is_file():
        for n,h in read('audit_archive_sha256.json').items():assert digest((ROOT/n).read_bytes())==h,n
    for lock in ['lock.json','planner_input_lock.json','planner_lock.json','transfer_lock.json']:
        if (ROOT/lock).is_file():
            for n,h in read(lock).items():assert digest((ROOT/n).read_bytes())==h
    assert len({r['episode'] for r in [*tr,*un,*se]})==len(tr)+len(un)+len(se)
    dataset=ROOT.parents[3]/'x20-session3-alfgames'/'json_2.1.1'
    if dataset.is_dir():
        assert all(digest((dataset/r['episode']).read_bytes())==r['game_sha'] for r in [*tr,*un,*se])
    # Rebuild training matrix on current container or from previously verified public terminal observations.
    native_path=ROOT/'audit_native_final.json.gz'
    native={r['episode']:r['final_admissible'] for r in json.loads(gzip.decompress(native_path.read_bytes()))} if native_path.exists() else {}
    hits=defaultdict(Counter);seen=Counter();rooms=[];missing=0;scount=0;steps=0
    for r in load_traces('train_logs'):
        entries=dict(r['samples']);short=scout_samples(r);missing+=len(entries)-len(short)
        if native:assert scout_samples(r,native[r['episode']])==entries
        else:assert all(entries[k]==v for k,v in short.items())
        start_room=sorted({c[6:].rsplit(' ',1)[0] for c in r['steps'][0]['available'] if c.startswith('go to ')})
        rooms.append({'episode':r['episode'],'samples':r['samples'],'room':start_room})
        for place,objs in entries.items():
            cl=place.rsplit(' ',1)[0];seen[cl]+=1
            for name in objs:hits[name][cl]+=1
        scount+=len(entries);steps+=len(r['steps'])
    assert rooms==read('training_rooms.json')
    assert {'hits':dict(hits),'seen':seen}==read('learned.json')
    starts={r['episode']:(r['observation'],r['commands']) for r in read('initial.json')}
    expected={'traces':(un,['none','recent','cursor','full','raw','rate']),'planner_traces':(un,['q_prior','q_shown','q_placebo','q_fused']),'transfer_traces':(un+se,['all_static','room_static','all_miss','room_miss'])}
    from policy import Actor,kind,order,goals
    from transfer import ConditionalActor
    class CurrentPlaceOnly(Actor):
        """Independent circular itinerary using place already tracked by every arm."""
        def search(self,target,commands):
            if 'open '+self.place in commands:return 'open '+self.place
            places=self.places
            pivot=(places.index(self.place)+1) if self.place in places else 0
            return self.travel(places[pivot:]+places[:pivot],commands) or 'look'
    cursor_noextra={'episodes':0,'actions':0}
    src=(ROOT/'planner_roll.py').read_text(encoding='utf8')
    cls=next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name=='PlannedActor')
    ns_pl={'Actor':Actor,'kind':kind,'order':order,'enc':canon}
    exec(ast.get_source_segment(src,cls),ns_pl)
    Planner=ns_pl['PlannedActor']
    learned=read('learned.json');room_records=read('training_rooms.json')
    plans=read('plans.json') if (ROOT/'plans.json').exists() else {}
    prefixes={};pairs={};counts={};unique_starts={};same_game_hash=defaultdict(list);nonematch=0;phase_excess=Counter()
    for r in [*tr,*un,*se]:same_game_hash[r['game_sha']].append(r['episode'])
    for folder,(episodes,arms) in expected.items():
        preds=set();completed=set();steps_total=0
        for r in load_traces(folder):
            ep=r['episode'];arm=r['arm']
            assert (ep,arm) not in pairs and (ep,arm) not in preds
            preds.add((ep,arm));completed.add(ep)
            initial=(r['initial'],r['steps'][0]['available'])
            assert initial==starts.setdefault(ep,initial)
            unique_starts[ep]=digest(canon(initial).encode())
            seq=b'';ns=len(r['steps'])
            sc=Planner if arm.startswith('q_') else ConditionalActor if arm in ('all_static','room_static','all_miss','room_miss') else Actor
            actor=sc(*initial,arm,learned)
            noextra=CurrentPlaceOnly(*initial,'none',{}) if arm=='cursor' else None
            if noextra:cursor_noextra['episodes']+=1
            actor.plans=plans;actor.records=room_records;actor.ranks={};trace_search=[];phase=0
            assert 0<ns<=50
            for i,s in enumerate(r['steps']):
                assert s['available']==sorted(set(s['available'])) and s['command'] in s['available']
                action=actor.act(s['available']);assert action==s['command'],(ep,arm,i)
                if noextra:
                    assert noextra.act(s['available'])==action
                    noextra.update(action,s['feedback'])
                    assert not noextra.history and noextra.cursor is None
                    cursor_noextra['actions']+=1
                actor.update(action,s['feedback']);assert actor.searched==s['searched']
                if actor.searched:trace_search.append((phase,actor.searched))
                if action.startswith(('take ','move ','put ')) and 'nothing happens' not in s['feedback'].lower():phase+=1
                if 'retained_search_entries' in s:assert len(actor.history)+int(actor.cursor is not None)==s['retained_search_entries']
                assert not s['done'] or i==ns-1
                # Any two rollouts with exactly the same past actions must see the same menu, outcome and observation.
                key=(ep,seq)
                cmd_state=digest(canon(s['available']).encode())
                ck=key+('commands',)
                assert prefixes.setdefault(ck,cmd_state)==cmd_state
                seq=hashlib.sha256(seq+s['command'].encode()).digest()
                feedback=digest(canon([s['feedback'],s['reward'],s['done'],s['won']]).encode())
                sk=(ep,seq,'transition')
                assert prefixes.setdefault(sk,feedback)==feedback
            assert r['steps'][-1]['done'] or ns==50
            phase_excess[arm]+=len(set(trace_search))-len({place for ph,place in trace_search})
            pairs[ep,arm]=(int(r['steps'][-1]['won']),ns if r['steps'][-1]['won'] else 50)
            steps_total+=ns
        all_requested={(r['episode'],a) for r in episodes for a in arms}
        if folder=='transfer_traces':
            all_requested.update((r['episode'],a) for r in se for a in ('full','rate'))
        assert preds<=all_requested
        if full:assert preds==all_requested,(folder,len(preds),len(all_requested))
        counts[folder]={'episodes':len(completed),'arms':len(preds),'commands':steps_total,'expected_arms':len(all_requested)}
    operation={'pick_and_place_simple':('',1),'pick_two_obj_and_place':('',2),'look_at_obj_in_light':('light',1),'pick_clean_then_place_in_recep':('clean',1),'pick_heat_then_place_in_recep':('heat',1),'pick_cool_then_place_in_recep':('cool',1)}
    parser_count=0
    for ep in unique_starts:
        family,obj,_,dst,scene=ep.split('/')[1].split('-')
        assert goals(starts[ep][0])==(obj.lower(),dst.lower(),*operation[family]),ep
        parser_count+=1
    exposure={};floors={r['episode']:r['floorplan'] for r in [*tr,*un,*se]}
    for label,rs in [('train',tr),('seen',se),('unseen',un)]:exposure[label]=sorted({floors[x['episode']] for x in rs})
    score_cells=0;contrast_cells=0
    if full:
        a=read('results.json');b=read('transfer_results.json')
        for name,rs,gr in [('base',un,a['all']),('transfer_unseen',un,b['valid_unseen']['all']),('transfer_seen',se,b['valid_seen']['all'])]:
            for arm,stats in gr.items():
                ids=[r['episode'] for r in rs]; outcomes=[pairs[ep,arm] for ep in ids]
                assert stats['won']==sum(v[0] for v in outcomes)
                expected_cost=sum(v[1] for v in outcomes)/len(ids)
                assert abs(stats.get('mean_capped_steps',stats.get('capped_steps_avg'))-expected_cost)<1e-10
                score_cells+=2
        for dataset,cases,contrasts in [('primary',un,a['contrasts']),('transfer-seen',se,b['valid_seen']['contrasts']),('transfer-unseen',un,b['valid_unseen']['contrasts'])]:
            for name,x in contrasts.items():
                active,base=name.split('-')
                costs=[];gains=[]
                for r in cases:
                    ep=r['episode']; left=pairs[ep,active];right=pairs[ep,base]
                    costs.append(left[1]-right[1]);gains.append(left[0]-right[0])
                assert x['W']==sum(v>0 for v in gains) and x['L']==sum(v<0 for v in gains)
                assert abs(x['win_difference']-sum(gains)/len(cases))<1e-10
                assert abs(x.get('mean_step_difference',x.get('step_difference'))-sum(costs)/len(cases))<1e-10
                contrast_cells+=4
    return {'source_rooms':exposure,'overlap_train_with_unseen_floors':len(set(exposure['train'])&set(exposure['unseen'])),'overlap_train_with_seen_floors':len(set(exposure['train'])&set(exposure['seen'])),'duplicate_game_digest_groups':sum(len(v)>1 for v in same_game_hash.values()),'train_steps':steps,'train_samples':scount,'missing_terminal_menu_in_original_logs':missing,'terminal_native_restored':bool(native),'rollouts':counts,'paired_starts':len(unique_starts),'goals_validated_against_metadata_only_during_audit':parser_count,'unique_prefix_checks':len(prefixes),'cursor_identical_no_extra_memory':cursor_noextra,'operational_phase_revisits_counted_as_repeats':phase_excess,'verified_score_cells':score_cells,'verified_contrast_cells':contrast_cells,'planning':verify_plans()}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--native',action='store_true');p.add_argument('--native-eval',action='store_true');p.add_argument('--final',action='store_true');opts=p.parse_args()
    if opts.native:train_replay()
    elif opts.native_eval:eval_replay()
    else:print(json.dumps(audit(opts.final),indent=2))

