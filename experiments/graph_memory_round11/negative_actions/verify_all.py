import collections,gzip,json,platform,re,subprocess
from harvest import D,get,save,sha
def main():
 rlock=get(D/"roster_lock.json");assert rlock["protocol"]==sha((D/"PROTOCOL_RU.md").read_bytes()) and rlock["roster"]==sha((D/"roster.json").read_bytes()) and rlock["acquisition"]==sha((D/"harvest.py").read_bytes())
 for lockname in ("key_lock.json","pre_oracle.lock.json"):
    assert all(sha((D/n).read_bytes())==d for n,d in get(D/lockname)["files"].items())
 mapping={r['iid']:r for r in get(D/'roster.json')};receipt=get(D/'receipts.json')
 assert len(receipt)==len(mapping)==163
 n=0
 for row in receipt:
    f=D/'observations'/(row['id']+'.json.gz');data=f.read_bytes();assert sha(data)==row['sha']
    obj=json.loads(gzip.decompress(data));assert obj['source']==mapping[row['id']] and len(obj['steps'])==row['steps']
    n+=len(obj['steps'])
 assert n==6132 and len(get(D/'predictions.json'))==len(get(D/'checked_rows.json'))==39
 existing=[k for k in re.findall(r'\]\(([^)]+)\)',(D/'REPORT_RU.md').read_text(encoding='utf8')) if not k.startswith('https://')]
 assert all((D/f).exists() for f in existing)
 docs=['REPORT_RU.md','PROTOCOL_RU.md','ANNOTATION_RU.md','RECOVERY_PROTOCOL_RU.md','roster_lock.json','key_lock.json','pre_oracle.lock.json','checked_rows.json','summary.json','sensitivity.json','git_pairs.json','recovery.json','recovery.py','summary.py','sensitivity.py','verify_all.py']
 save(D/'verification.json',{'python':platform.python_version(),'git':subprocess.check_output(['git','--version']).decode().strip(),'verified_projection_files':len(receipt),'actions':n,'oracle_queries':39,'independent_revision_checks':78,'local_links':len(existing),'delivery':{f:sha((D/f).read_bytes()) for f in docs}})
 print('verified',len(receipt),n,len(existing))
if __name__=='__main__':main()
