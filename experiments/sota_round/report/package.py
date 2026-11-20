from pathlib import Path
import argparse
import hashlib
import os
import zipfile
root=Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="Package the tracked research records and reproducibility files.")
parser.add_argument('--output', type=Path, default=root.parents[1]/'outputs'/'agent-memory-benchmark-records.zip')
dst = parser.parse_args().output.resolve()
dst.parent.mkdir(parents=True, exist_ok=True)
parts={}
def take(path):
    if path.is_file() and path.suffix!='.pyc' and '__pycache__' not in path.parts:
        parts[path.relative_to(root).as_posix()]=path.read_bytes()
def pattern(folder,pat):
    for p in (root/folder).glob(pat):take(p)
for f in ['README_RU.md','verify.py']:take(root/f)
for folder in ('dretr','retainer'):
    m=root/folder/'MANIFEST.sha256'; take(m)
    for line in m.read_text(encoding='utf8').splitlines():
        h,n=line.split('  ',1);p=root/folder/n;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;take(p)
for f in ('comparison.md','rescore.py','verify_official.py','official_retrieval.py','official_qa_metrics.py.txt','official_verification.json','recount.json','recount_per_question.csv','papr_ranks.jsonl','official_scoring_metadata.json'):
    take(root/'comparators'/f)
for pat in ('gbrain_*.ndjson.gz','papr_*.grades.jsonl'):
    pattern('comparators',pat)
for pt in ('*.py','*.md','*.json','*.csv','hosted_decisions.jsonl','run/*.json','run/*.jsonl','run/*.csv','followup/predictions.jsonl','followup/results.json','followup/per_question.csv'):
    pattern('boundary',pt)
for folder in ('action','action_text'):
    for pat in ('*.py','*.md','*.json','*.jsonl','*.csv','*.zip','*.log','logs/*.json'):pattern(folder,pat)
for folder in ('coding','coding_holdout'):
    for pat in ('*.py','*.md','*.json','*.csv','*.jsonl','receipts/*.json','predictions/*.json'):
        for p in (root/folder).glob(pat):
            if p.name!='bench.final.public.jsonl':take(p)
for pat in ('LICENSE','README.md','pyproject.toml','**/*.py'):
    pattern('coding/upstream',pat)
for folder in ('vibe','vibe/qwen38_27b','vibe/in_loop','vibe_memory','vibe_solver','vibe_qwen38','prior_files','within_task','swe_context','swe_context/matched_reader','read_cache','read_cache/replication'):
    for pat in ('*.py','*.cpp','*.cs','*.sh','*.ps1','*.md','*.json','*.jsonl','*.csv','*.zip','*.toml','*.yaml','*.txt','*.png','*.tsv','*.sha256','*.log'):
        pattern(folder,pat)
pattern('swe_context/logs','*.log')
run_directory=Path(os.environ.get('SWE_CONTEXT_DATA','D:/CodexResearch/x20-swe-context'))
for name in ('cards-mask.log','rank.log','rank-mask.log','rank-mask-resumed.log','cross-encoder.log',
             'cross-encoder-mask.log','cross-encoder-mask-resumed.log','download-model.log','choose.log'):
    transcript=run_directory/name
    member='swe_context/logs/'+name
    if member not in parts and transcript.is_file():
        parts[member]=transcript.read_bytes()
for f in ['tracks.py','boundary_report.py','systems.py','holdout.py','build.py','layout.py','package.py','visualcheck.py','next.py','actions.py','vibe_report.py','vibe_memory.py','prior_files.py','strong_report.py','within_task.py','read_cache.py','swe_context_report.py','matched_reader.py','power-scenarios.json','design_power.py']:
    take(root/'report'/f)
manifest='\n'.join(hashlib.sha256(parts[n]).hexdigest()+'  '+n for n in sorted(parts))+'\n'
temporary=dst.with_suffix('.partial.zip')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as archive:
    for n in sorted(parts):archive.writestr(n,parts[n])
    archive.writestr('MANIFEST.sha256',manifest.encode())
temporary.replace(dst)
print(len(parts),'files',dst.stat().st_size,'bytes')

