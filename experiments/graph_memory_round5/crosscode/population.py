"""Paired screening by equal messages before opening the authors' targets."""
from prepare import *
def main():
    banned=banned_projects();out=[];pop=[]
    name="java/line_completion_rg1_unixcoder_cosine_sim.jsonl"
    with tarfile.open(D/"crosscodeeval_data.tar.xz") as tf:
        for rawrow in tf.extractfile(name):
            x=json.loads(rawrow); m=x["metadata"];repo=m["repository"]; ctx,ct=trim(x["prompt"],1536,True)
            fs=candidates(x);doc=x["crossfile_context"]["text"]
            h=storage.sha(ctx);eligible=bool(fs) and not bool(BAD.search("\n".join([repo,m["file"],ctx,doc])))
            cross=norm(re.sub(r"-[0-9a-fA-F]{6,40}$","",repo)) in banned
            z=dict(id=m["task_id"],repo=repo,ctx_sha=h,eligible=eligible,known=cross,changed=False)
            if eligible:
                order,events=relay(ctx,fs);given=list(range(len(fs)))
                a=trim(render(doc,fs,given),512);b=trim(render(doc,fs,order),512)
                z.update(changed=a[0]!=b[0],reranked=given!=order,hashes=[storage.sha(a[0]),storage.sha(b[0])])
                if z["changed"]:
                    out.append(dict(id=z["id"],repo=repo,ctx=ctx,ctx_tokens=ct,snippets={"order":a,"bridge":b},order=order,observed_edge=events,known=cross))
            pop.append(z)
    storage.save("E_population.json.gz",pop);storage.save("E_packets.json.gz",out)
    names=["E_PROTOCOL_RU.md","PROTOCOL_RU.md","population.py","prepare.py","infer_cross.py","E_packets.json.gz","E_population.json.gz","D_data_lock.json"]
    storage.save("E_data_lock.json",dict(sha={n:storage.sha((D/n).read_bytes()) for n in names},total=len(pop),eligible=sum(z["eligible"] for z in pop),changed=len(out),new_project=sum(z["eligible"] and not z["known"] for z in pop)))
    print(storage.read("E_data_lock.json"),flush=True)
if __name__=="__main__":main()

