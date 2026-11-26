"""First two admissible candidates in fixed order; records all exclusions through selection."""
from screen import *
import datetime
SCOPE={'getmoto/moto':'network_service_infrastructure','vyperlang/vyper':'blockchain_compiler','cs-si/eodag':'external_network_service','aws-cloudformation/cfn-lint':'network_service_infrastructure','http-apis/hydrus':'network_service_infrastructure','sinaptik-ai/pandas-ai':'external_model_inference'}
def archive(r):
    CACHE.mkdir(parents=True,exist_ok=True)
    url=f"https://codeload.github.com/{r['repo']}/tar.gz/{r['base_commit']}"
    p=CACHE/(r['instance_id']+'.tar.gz')
    if not p.exists():
        subprocess.run(['curl.exe','--retry','2','--fail','-L','-sS','--max-filesize',str(40*2**20),'--max-time','90','-o',str(p)+'.part',url],check=True)
        Path(str(p)+'.part').replace(p)
    with tarfile.open(p) as f:
        members=f.getmembers(); size=sum(m.size for m in members if m.isfile()); files=[m for m in members if m.isfile()]
        licenses=[m for m in files if len(Path(m.name).parts)==2 and Path(m.name).name.lower().startswith(('license','licence','copying'))]
        license_summary=[{'path':m.name.split('/',1)[1],'sha256':hashlib.sha256(f.extractfile(m).read()).hexdigest()} for m in licenses]
    return {'url':url,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'bytes':p.stat().st_size,'regular_bytes':size,'file_count':len(files),'python_files':sum(m.name.endswith('.py') for m in files),'licenses':license_summary}
def main():
    ledger=[]; selected=[]
    for i,r in enumerate(rows()):
        ident=r['instance_id']; reason=eligible(r); extra={}
        if reason=='review':
            reason=SCOPE.get(r['repo'].lower(),'archive')
        if reason=='archive':
            data=archive(r); extra['archive']=data
            reason='selected' if data['licenses'] and data['regular_bytes']<=120*2**20 and data['python_files']<=1500 else 'source_size_or_license'
            if r['repo'] in [s['repo'] for s in selected]:reason='backup_same_repo'
        if reason=='selected':
            selected.append(dict(repo=r['repo'],instance=ident,rank=i+1,base=r['base_commit'],histories=len(set(ids(r))),f2p=len(r['FAIL_TO_PASS']),p2p=len(r['PASS_TO_PASS']),archive=extra['archive']))
        ledger.append(dict(rank=i+1,instance=ident,reason=reason,**extra))
        if len(selected)==2:break
    save(D/'screen.json',dict(rows=len(rows()),protocol_sha256=hashlib.file_digest((D/'PROTOCOL.md').open('rb'),'sha256').hexdigest(),selected=selected,ledger=ledger));print([(s['instance'],s['f2p'],s['p2p'],s['archive']['bytes']) for s in selected])
if __name__=='__main__':main()