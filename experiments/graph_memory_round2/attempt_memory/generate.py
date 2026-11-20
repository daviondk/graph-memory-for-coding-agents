import json,re
from prepare import HERE,read,sha,save
from llm import model_call

def extract(s):
    blocks=re.findall(r"(?is)\x60{3}(?:python|py)?[ \t]*\r?\n(.*?)(?:\x60{3}|\Z)",s)
    return (blocks[0] if blocks else s).strip()+"\n"
def main():
    its=read(HERE/"inputs.json")
    assert sha((HERE/"inputs.json").read_bytes())==read(HERE/"input_lock.json")["inputs_sha"]
    attempts=["Implement the task directly.","Consider edge cases, then implement the task.","Use an independently chosen implementation."]
    jobs=[(r,j) for r in its if r["panel"]=="fresh" for j in range(3)]
    jobs.sort(key=lambda p:sha("schedule|"+str(p[0]["id"])+"|"+str(p[1])))
    for k,(it,j) in enumerate(jobs):
        dest=HERE/"programs"/str(it["id"])
        text="Task: "+it["spec"]+"\nRequired interface: "+it["sig"]+"\n"+attempts[j]
        sys_prompt="Write a small correct Python function. Output only Python code, no Markdown, prose, or tests. Use the exact interface. Use standard library pure computation only."
        seed=int(sha(f"candidate|{it['id']}|{j}")[:7],16)
        rec=model_call(sys_prompt,text,384,seed,.45)
        code=extract(rec["reply"]["choices"][0]["message"].get("content","") or "")
        (dest/f"{j}.py").write_text(code,encoding="utf8")
        save(dest/f"{j}.json",{"call":rec["key"],"code_sha":sha(code),"usage":rec["reply"]["usage"],"finish":rec["reply"]["choices"][0]["finish_reason"]})
        if (k+1)%12==0:print("generated",k+1,"of",len(jobs),flush=True)
    locks={str(f.relative_to(HERE)):sha(f.read_bytes()) for f in (HERE/"programs").glob("*/*.py")}
    save(HERE/"candidate_lock.json",locks)
if __name__=="__main__":main()

