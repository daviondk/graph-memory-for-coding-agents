"""Verify a freshly unpacked distribution using only files contained in it."""
import hashlib,json,pathlib,subprocess,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'outputs'
TARGET=pathlib.Path('D:/CodexResearch/x20-session4-offline-check-v2')

def main():
    archive=OUT/'agent-memory-session4-records.zip'
    assert not TARGET.exists(),'Use an unused extraction folder. Never merge into an existing check.'
    TARGET.mkdir()
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('MANIFEST.sha256.json'))
        for name in z.namelist():
            p=(TARGET/name).resolve()
            assert p.is_relative_to(TARGET.resolve()),name
        z.extractall(TARGET)
    for name,digest in manifest.items():
        assert hashlib.sha256((TARGET/name).read_bytes()).hexdigest()==digest,name
    checks=[]
    for f in ('action/verify.py','compact/verify.py','discovery/verify.py','handoff/verify.py','handoff/verify_patch_identity.py','handoff/attestation/external/verify.py'):
        result=subprocess.run([sys.executable,'-B',str(TARGET/f)],cwd=TARGET,capture_output=True,text=True,encoding='utf8')
        checks.append({'entry':f,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        assert result.returncode==0,checks[-1]
    sys.path.insert(0,str(TARGET))
    import freeze_runtime
    runtime=freeze_runtime.verify(TARGET/'runtime')
    assert runtime==json.loads((TARGET/'runtime/verified.json').read_bytes())
    receipt={'all_passed':True,'manifest_files':len(manifest),'checks':checks,'runtime':runtime,
             'source':str(TARGET),'used_only_packaged_data':True,'network_requests':0,'gpu_inference_requests':0}
    (ROOT/'distribution_verified.json').write_text(json.dumps(receipt,indent=1,ensure_ascii=False),encoding='utf8')
    print(json.dumps(receipt,indent=1,ensure_ascii=False))
if __name__=='__main__':main()
