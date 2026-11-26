"""Exercise the standalone HTML in offline Chromium and compare each state with sealed data."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
R54 = HERE.parents[1]/"graph_memory_round54/code_links"
DEFAULT = "a726f272e7ddbd50bac4face"

def read(path):
    return json.load(gzip.open(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", type=Path, default=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"))
    parser.add_argument("--screenshots",type=Path)
    args = parser.parse_args()
    ref = read(R54/"graded-rows.json.gz")
    ranked = read(HERE/"expanded-ranks.json.gz")
    input_rows = read(R54/"forecasts.json.gz")
    history = read(HERE/"history.json.gz")
    expected = {}
    for q,r in ranked.items():
        ax=input_rows[q]["anchor"]
        by_path={}
        for p,*_ in r["evidence"]:
            by_path[p]=[s for s,k,paths in history[r["base"]]["history"] if 2<=k<=20 and p in paths and ax in paths]
        expected[q]=dict(lexical=r["ranked"]["lexical"],graph=r["ranked"]["corroborated"],anchor=ax,reference=ref[q]["gold"],base=r["base"],evidence=by_path)
    verifier = r'''all=>{
      const el=id=>document.getElementById(id);const check=(v,msg)=>{if(!v)throw new Error(msg)};
      const rank=()=>Array.from(el("rank").querySelectorAll("code"),c=>c.textContent);
      const gold=()=>Array.from(el("gold").querySelectorAll("code"),c=>c.textContent);
      const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
      const choose=(e,v)=>{e.value=v;e.dispatchEvent(new Event("change",{bubbles:true}))};
      let states=0, selectedCandidates=0, checkedCommits=0, changed=0, gained=0;
      check(el("task").options.length===54,"task list");
      for(const [id,r] of Object.entries(all)){
        choose(el("task"),id);check(el("anchor").textContent===r.anchor&&el("base").textContent===r.base,"record "+id);
        check(el("reference").hidden&&gold().length===0,"initial labels "+id);
        for(const policy of ["lexical","graph"]){
          el(policy).click();check(el(policy).getAttribute("aria-pressed")==="true","pressed "+policy);
          check(equal(rank(),r[policy]),"ranks "+id);
          check(el("reference").hidden&&el("rank").querySelectorAll(".hit").length===0,"hidden targets");states++;
          if(policy==="graph"){
            check(Boolean(el("candidate"))===Boolean(Object.keys(r.evidence).length),"evidence toggle "+id);
            if(el("candidate")){
              const names=Array.from(el("candidate").options,c=>c.textContent);
              check(equal(names.slice().sort(),Object.keys(r.evidence).sort()),"candidate inventory "+id);
              if(r.graph[4]!==r.lexical[4])check(names[0]===r.graph[4],"winning candidate");
              for(let i=0;i<names.length;i++){
                choose(el("candidate"),String(i));
                const shas=Array.from(el("evidence").querySelectorAll(".hash"),a=>a.textContent);
                check(equal(shas,r.evidence[names[i]]),"witness "+id);
                checkedCommits+=shas.length;selectedCandidates++;
              }
            }
          } else {check(!el("candidate")&&el("evidence").querySelectorAll(".hash").length===0,"lexical evidence")}
          el("reveal").click();
          check(!el("reference").hidden&&el("reveal").getAttribute("aria-expanded")==="true","reference reveal");
          check(equal(gold(),r.reference),"reference files "+id);
          const hits=r[policy].filter(p=>r.reference.includes(p)).length;
          check(el("rank").querySelectorAll(".hit").length===hits,"visible hit marks");
          check(el("hits").textContent==="Retrieved "+hits+" of "+r.reference.length+" annotated files with five reads.","hit summary");
          states++;el("reveal").click();
        }
        changed+=Number(r.graph[4]!==r.lexical[4]);gained+=Number(r.reference.includes(r.graph[4]))-Number(r.reference.includes(r.lexical[4]));
      }
      const examples=el("examples").querySelectorAll("button");
      for(const b of examples){b.click();check(Boolean(all[el("task").value]),"example control")}
      examples[0].click();
      return {task_count:Object.keys(all).length,policy_reference_states:states,inspected_candidates:selectedCandidates,
              verified_witness_visits:checkedCommits,changed_fifth_files:changed,net_additional_reference_files:gained,
              example_controls:examples.length};
    }'''
    with sync_playwright() as tool:
        browser=tool.chromium.launch(executable_path=str(args.chromium),headless=True)
        context=browser.new_context(offline=True,viewport={"width":1280,"height":800},device_scale_factor=1)
        pg=context.new_page()
        errors=[];network=[]
        pg.on("pageerror",lambda e:errors.append(str(e)))
        pg.on("request",lambda req:network.append(req.url) if req.url.startswith(("http://","https://")) else None)
        pg.goto((HERE/"replay.html").as_uri())
        assert pg.locator("#task").input_value()==DEFAULT
        note = pg.locator("#budget-note").inner_text()
        assert all(s in note for s in ["50.46%", "48.92%", "41.20%", "43.36%", "-2.16 percentage points"])
        receipt=pg.evaluate(verifier,expected)
        receipt["two_budgets_visible"] = True
        assert receipt["policy_reference_states"]==216 and receipt["changed_fifth_files"]==12 and receipt["net_additional_reference_files"]==2
        screens=[]
        for width,height in [(1280,800),(390,844)]:
            pg.set_viewport_size(dict(width=width,height=height))
            assert pg.evaluate("document.documentElement.scrollWidth<=innerWidth"), (width,"horizontal overflow")
            if args.screenshots:
                args.screenshots.mkdir(parents=True,exist_ok=True)
                pg.screenshot(path=str(args.screenshots/("replay-"+str(width)+".png")),full_page=True)
            screens.append([width,height])
        assert not errors and not network
        receipt.update(browser=browser.version, screen_sizes=screens, javascript_errors=errors, network_requests=network,
                       sha256=hashlib.sha256((HERE/"replay.html").read_bytes()).hexdigest())
        browser.close()
    (HERE/"replay-ui-audit.json").write_bytes((json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode())
    print(receipt)


if __name__=="__main__":
    main()
