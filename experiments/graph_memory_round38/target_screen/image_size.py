"""Inspect the official public registry manifest without fetching image layers or storing tokens."""
from screen import *
import urllib.parse as u
def get(url,headers=()):
    cmd=['curl.exe','--retry','1','--silent','--fail','--show-error','--max-time','30']
    for h in headers:cmd+=['-H',h]
    return subprocess.check_output([*cmd,url])
def main():
    for a in json.loads((D/'screen.json').read_text())['selected']:
        e=D/'evaluator'/a['instance'];img=json.loads((e/'case.json').read_text())['image_name'].split('/',1)[1];repo,tag=img.split(':');prefix='https://registry-1.docker.io/v2/'+repo+'/manifests/'
        token=json.loads(get('https://auth.docker.io/token?'+u.urlencode(dict(service='registry.docker.io',scope='repository:'+repo+':pull'))))['token']
        headers=['Authorization: Bearer '+token,'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json']
        b=get(prefix+tag,headers);m=json.loads(b)
        if 'manifests' in m:
            amd=next(q for q in m['manifests'] if q.get('platform',{}).get('os')=='linux' and q['platform'].get('architecture')=='amd64')
            b=get(prefix+amd['digest'],headers);m=json.loads(b);assert 'sha256:'+hashlib.sha256(b).hexdigest()==amd['digest']
        out=dict(image=img,manifest='sha256:'+hashlib.sha256(b).hexdigest(),layers=len(m['layers']),compressed_bytes=sum(l['size'] for l in m['layers']));save(e/'image-size.json',out);print(out)
if __name__=='__main__':main()