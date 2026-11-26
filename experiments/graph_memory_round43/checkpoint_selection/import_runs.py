"""Read the completed original runs on the evidence machine. Nothing is trained or written outside this audit."""
import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZipInfo, ZIP_STORED

D=Path(__file__).resolve().parent
SEEDS=(13,17,29,37,41)
ARMS=('full_rgcn','wo_chunk_adjacency')

def raw(p):return p.read_bytes()
def hashed(p):return sha256(raw(p)).hexdigest()
def read(p):
    data=raw(p)
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
def write(p,obj):
    b=(json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b)
def add(z,name,path):
    info=ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
    z.writestr(info,raw(path),compress_type=ZIP_STORED)
def tensors(state):
    out={}
    for k,t in sorted(state.items()):
        arr=t.detach().cpu().contiguous().numpy()
        out[k]=[str(arr.dtype),list(arr.shape),sha256(arr.tobytes()).hexdigest()]
    return out

def project(work,replay,native):
    w=work.resolve();r34=w/'graph_memory_round34/dev_metric';r37=w/'graph_memory_round37/native_five_seeds';r22=w/'graph_memory_round22/native_multiseed/official580'
    sys.path.insert(0,str(r34));import tap
    tf=tap.s.torch
    r34m=read(r34/'manifest.json');r37c=read(r37/'canonical-manifest.json');r37b=read(r37/'metric-matched-manifest.json')
    def ref(path):
        return [path.relative_to(w).as_posix(),hashed(path)]
    docs=D/'originals';docs.mkdir(exist_ok=True)
    sources={}
    for name,p in {'r34-dev':r34/'PROTOCOL_RU.md','r34-strict':r34.parent/'native_comparison/PROTOCOL_RU.md',
                   'r37-five-seed':r37/'PROTOCOL_RU.md'}.items():
        (docs/(name+'.txt')).write_bytes(raw(p));sources[name]=ref(p)
    for name,p in {'r34-plan':r34/'plan.json','r37-plan':r37/'plan.json','r34-all-dev':r34/'all-dev-seal.json',
                   'r34-final':r34/'budget-selected-comparison.json','r37-canonical':r37/'canonical-complete.json',
                   'r37-matched':r37/'metric-matched-complete.json','r37-final':r37/'final.json','r34-manifest':r34/'manifest.json',
                   'r37-canonical-manifest':r37/'canonical-manifest.json','r37-matched-manifest':r37/'metric-matched-manifest.json'}.items():
        (docs/(name+'.json')).write_bytes(raw(p));sources[name]=ref(p)
    seals=read(r34/'all-dev-seal.json')
    audit={};test_sources={}
    for seed in SEEDS:
        canon_file=r37/f'canonical-{seed}.json.gz';match_file=r37/f'metric-matched-{seed}.json.gz'
        assert r37c[canon_file.name]==hashed(canon_file) and r37b[match_file.name]==hashed(match_file)
        canon=read(canon_file);matched=read(match_file);assert set(canon)==set(matched)
        triples={};tests=[]
        for arm in ARMS:
            tag=f'{seed}-{arm}'
            pub=r22/f'seed-{seed}'/arm;ext=replay/f'seed-{seed}'/arm
            choice=r34/f'dev-selection-{tag}.json'
            assert hashed(choice)==seals[choice.name]==r34m[choice.name]==hashed(ext/'dev-selection.json')
            meta=read(choice);attempt=ext/meta['attempt'];fit=read(pub/'fit.json')
            ck0=native/f'seed-{seed}'/fit['attempt']/'best.pt';ck1=attempt/'best.pt'
            assert hashed(ck0)==fit['checkpoint'] and hashed(r22/f'seed-{seed}/train-pairs.json.gz')==meta['pair_sha']==fit['training_pairs']
            assert hashed(r22/'split.json.gz')==meta['dev_ids']
            official=tap.s.inf.load_rgcn_checkpoint(ck0,map_location='cpu').payload
            repeated=tap.s.inf.load_rgcn_checkpoint(ck1,map_location='cpu').payload
            base=tensors(official['model_state_dict']);again=tensors(repeated['model_state_dict'])
            assert set(base)==set(again) and (base==again)==meta['same_recall_winner_weights']
            re=int(meta['repeated_epoch']);sel=int(meta['selected']['epoch'])
            assert meta['original_epoch']==official['epoch'] and re==repeated['epoch']
            assert again==tensors(tf.load(attempt/f'epoch-{re}.pt',weights_only=True,map_location='cpu'))
            budget=tensors(tf.load(attempt/f'epoch-{sel}.pt',weights_only=True,map_location='cpu'))
            nativelog=read(pub/'checkpoint.json');relog=read(attempt/'checkpoint.json')
            assert nativelog['epoch']==official['epoch'] and relog['epoch']==re
            public=read(r34/f'test-rank-seal-{tag}.json')
            assert public['dev']==hashed(r34/'all-dev-seal.json') and public['weight']==meta['selected']['weight'] and public['ranks']==hashed(ext/'test-ranks.json.gz')
            test=r34/f'test-results-{tag}.json.gz';assert hashed(test)==r34m[test.name];tests.append(read(test))
            shapes={}
            with ZipFile(D/f'dev-{tag}.zip','w') as arch:
                add(arch,'ledger.json',choice);add(arch,'native-checkpoint.json',pub/'checkpoint.json');add(arch,'replay-checkpoint.json',attempt/'checkpoint.json')
                for row in meta['ledger']:
                    epoch=row['epoch'];scores=attempt/f'metrics-{epoch}.json.gz';order=attempt/f'ranks-{epoch}.json.gz';pt=attempt/f'epoch-{epoch}.pt'
                    assert [hashed(p) for p in (scores,order,pt)]==[row[k] for k in ('outcomes','ranks','weight')]
                    ranks=read(order)
                    if epoch==0:shapes={q:frozenset(v) for q,v in ranks.items()}
                    assert ranks.keys()==shapes.keys() and all(len(v)==len(shapes[q]) and set(v)==shapes[q] for q,v in ranks.items())
                    assert set(read(scores))==set(shapes) and sum(map(len,shapes.values()))==72624
                    add(arch,f'metrics-{epoch}.json.gz',scores)
            ids=sorted(shapes);assert len(ids)==580 and not set(ids)&canon.keys()
            audit[tag]={'keys':len(base),'canonical':base,'replay_recall':again,'replay_budget':budget,'original_epoch':official['epoch'],'recalled_epoch':re,'budget_epoch':sel,
                        'canonical_checkpoint':hashed(ck0),'replay_checkpoint':hashed(ck1),'replay_budget_weights':meta['selected']['weight'],
                        'train_pairs':meta['pair_sha'],'dev_split':meta['dev_ids'],'original_fit':ref(pub/'fit.json'),'canonical_seed_file':ref(canon_file),
                        'dev_ids':sha256('\n'.join(ids).encode()).hexdigest(),'dev_log':ref(choice),'test_scores':ref(test),'test_ranking_seal':public}
        for q,row in canon.items():
            o=matched[q];assert row[:3]==o[:3] and all(t[q][0]==row[0] for t in tests)
            assert o[-2:]==[t[q][1] for t in tests]
            assert len(row)==5 and len(o)==5 and all(len(v)==6 for v in row[1:]+o[1:])
            triples[q]=row+o[-2:]
        write(D/f'paired-{seed}.json.gz',triples);test_sources[str(seed)]={'paths':[ref(canon_file),ref(match_file)],'json_sha256':[sha256(gzip.decompress(raw(f))).hexdigest() for f in (canon_file,match_file)]}
    write(D/'imports.json',{'originals':sources,'test_sources':test_sources,'tensors':audit})

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--work',type=Path,required=True);cli.add_argument('--replay',type=Path,required=True);cli.add_argument('--native',type=Path,required=True);a=cli.parse_args();project(a.work,a.replay,a.native)

