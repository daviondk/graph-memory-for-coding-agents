/** Map observed rows with the published CodeMirror operator. No target reads or texts are scored here. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { gzipSync, gunzipSync } from "node:zlib";

const dir = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const entry = require.resolve("@codemirror/state", {
  paths: [dir, process.env.EDITOR_BASELINE_DEPS || "D:/CodexResearch/x20-r37-editor-deps"]
});
const { ChangeSet, MapMode } = require(entry);
const sha = value => createHash("sha256").update(value).digest("hex");
const sourcePath = path.join(dir, "../code_visibility/events.json.gz");
const binary = fs.readFileSync(sourcePath);
const events = JSON.parse(gunzipSync(binary));
const CAP = 128;

function select(file, pairs, size) {
  const keys = pairs.map(([n,s]) => [sha("R37-128|"+file+"|"+n),n,s]);
  keys.sort((a,b)=>a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
  return keys.slice(0,size).map(([,n,s])=>[n,s]);
}
function transfer(file, oldRows, edit) {
  const seen = new Map(select(file,edit.rows,CAP));
  if (edit.k !== null) {
    const start = edit.k-1;
    const oldWidth = edit.old_breaks+1;
    const newWidth = oldWidth+edit.delta;
    const length = Math.max(start+oldWidth,...oldRows.map(r=>r[0]));
    const change = ChangeSet.of({from:start,to:start+oldWidth,insert:".".repeat(newWidth)},length);
    const shifted = [];
    for (const [line,hash] of select(file,oldRows,CAP)) {
      const pos = change.mapPos(line-1,1,MapMode.TrackAfter);
      if (pos !== null && !seen.has(pos+1)) shifted.push([pos+1,hash]);
    }
    for (const [line,hash] of select(file,shifted,CAP-seen.size)) seen.set(line,hash);
  }
  return [...seen].sort((a,b)=>a[0]-b[0]);
}
const output = {};
for (const [rid,run] of Object.entries(events)) {
  const scopes = new Map();
  for (const [idx,type,file,value] of run.events) {
    let scope = scopes.get(file);
    if (type === "write_start" && scope) scope.starts.push(idx);
    if ((type === "edit" || type === "other") && scope) scope.ops.push([idx,type,value]);
    if (type !== "read") continue;
    if (scope && scope.ops.length === 1 && scope.starts.length === 1 && scope.rows.length && value.length) {
      const [end,op,edit] = scope.ops[0];
      if (op === "edit" && edit.matched && scope.starts[0]===edit.action_index &&
          scope.prev<edit.action_index && edit.action_index<end && end<idx) {
        const key = sha([rid,scope.prev,end,idx].join("|"));
        if (key in output) throw new Error("duplicate");
        output[key] = transfer(file,scope.rows,edit);
      }
    }
    scopes.set(file,{prev:idx,rows:value,starts:[],ops:[]});
  }
}
const artifact = gzipSync(Buffer.from(JSON.stringify(output)+"\n"),{level:9});
fs.writeFileSync(path.join(dir,"predictions.json.gz"),artifact);
const pack = JSON.parse(fs.readFileSync(path.join(path.dirname(entry),"../package.json")));
if (pack.version !== "6.7.6" || Object.keys(output).length !== 1282) throw new Error("dependency or cohort mismatch");
const receipt = {library:pack.name,version:pack.version,entry_sha256:sha(fs.readFileSync(entry)),
  node:process.version,source_sha256:sha(binary),questions:Object.keys(output).length,output_sha256:sha(artifact),
  protocol_sha256:sha(fs.readFileSync(path.join(dir,"PROTOCOL_RU.md"))),implementation_sha256:sha(fs.readFileSync(fileURLToPath(import.meta.url)))};
fs.writeFileSync(path.join(dir,"prediction-seal.json"),JSON.stringify(receipt,null,2)+"\n");
console.log(JSON.stringify(receipt));

