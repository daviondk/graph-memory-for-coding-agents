"""Privately fetch original repository pre-mutation source and derive canonical reference. Never used by actor/selection."""
from concurrent.futures import ThreadPoolExecutor
import ast,gzip,hashlib,json
from common import ROOT,rows,rel,success
from pipeline import data
from live_prepare import get,quote
L=ROOT/'live'
def canonical(text):
    try:return ast.dump(ast.parse(text),include_attributes=False)
    except (ValueError,SyntaxError):return None
def hashtext(t):return hashlib.sha256(t.encode()).hexdigest() if t is not None else None
def original(c):
    repo,short=c['repo'].split('.',1);owner,name=repo.split('__',1);p=c['path'];url=f'https://raw.githubusercontent.com/{owner}/{name}/{short}/{quote(p)}';status,b=get(url)
    return c['instance'],{'url':url,'code':status,'blob_sha256':hashlib.sha256(b).hexdigest(),'data':b}
def main():
    cases=json.loads((L/'cohort.json').read_bytes());selected={c['instance'] for c in cases}
    data_by={r['instance']:r for k in range(8) for r in data('test',k) if r['instance'] in selected}
    with ThreadPoolExecutor(8) as ex:g=dict(ex.map(original,cases))
    gold=[]
    for c in cases:
        i=c['instance'];v=g[i];body=v.pop('data');snap=gzip.decompress((L/'snapshots'/c['snapshot']).read_bytes()).decode('utf8');ast0=canonical(snap);assert ast0 is not None
        try:ref=body.decode('utf8').replace('\r\n','\n') if v['code']==200 else None
        except UnicodeError:ref=None
        ref_ast=canonical(ref) if ref is not None else None
        if ref is not None:
            dest=L/'references'/v['blob_sha256'];dest.parent.mkdir(exist_ok=True);dest.with_suffix('.gz').write_bytes(gzip.compress(body,mtime=0))
        mark=None
        for tool,args,fb in data_by[i]['events'][c['cut']:c['cut']+4]:
            if args.get('command')=='str_replace' and args.get('old_str'):
                mark={'path':rel(args.get('path')),'old_str':args['old_str'],'new_str':args.get('new_str',''),'accepted':success('str_replace',rel(args.get('path')),fb)};break
        gold.append({'id':i,'path':c['path'],'snapshot':c['snapshot'],'base_reference':v,'pre_ast_sha':hashtext(ast0),'ref_ast_sha':hashtext(ref_ast),'historical':mark})
    (L/'outcomes.json').write_text(json.dumps(gold,ensure_ascii=True))
    print('references',sum(x['ref_ast_sha'] is not None for x in gold),'repairable target files',sum(x['ref_ast_sha'] is not None and x['ref_ast_sha']!=x['pre_ast_sha'] for x in gold),'same-next-accepted',sum(bool(x['historical'] and x['historical']['accepted'] and x['historical']['path']==x['path']) for x in gold))
if __name__=='__main__':main()
