"""Prepare a preregistered conservative attribution arm without reading any outcomes."""
import sys,re,shutil,json,collections
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
import writer
from common import read,write,sha,canon
from prepare_solver import anonymize

ORIGINAL_CHECK=writer.check_event
def eligible(cmd):
    if any(token in cmd for token in ('<<','|',';','>','<','\x60','$(')):
        return False
    candidates=list(writer.TEST.finditer(cmd))
    if len(candidates)!=1:
        return False
    found=candidates[0]
    if cmd[:found.start()].strip() or cmd[found.end():].strip():
        return False
    invocation=found[1]
    if any(token in invocation for token in ('&','\n','\r')):
        return False
    prefix=cmd[found.start():found.start(1)]
    return re.fullmatch(r'\s*(?:cd [\w./~+-]+\s*&&\s*)?(?:[\w./-]+=\S+\s+)*',prefix) is not None

def strict_check(cmd,event):
    return ORIGINAL_CHECK(cmd,event) if eligible(cmd) else None

def main():
    clean=read('clean/reader_inputs.json.gz')
    baseline=read('receipts.json.gz')
    counts=collections.Counter()
    changed=[]
    rows={}
    writer.check_event=strict_check
    for iid in sorted(clean):
        for alias,model in [('claude','claude'),('codex','gemini')]:
            record=read('records/'+model+'/'+iid+'.json.gz')
            original=baseline[model+'|'+iid]
            updated=writer.project(record)
            rows[model+'|'+iid]=updated
            excluded={j for j,t in enumerate(record['turns']) if not eligible(t['cmd'])}
            affected=[e for e in original['events'] if e['j'] in excluded]
            affected_pairs=[e for e in affected if e['paired']]
            counts[model+'_candidates']+=1
            counts[model+'_all_events']+=len(original['events'])
            counts[model+'_excluded_events']+=len(affected)
            counts[model+'_excluded_paired_events']+=len(affected_pairs)
            counts[model+'_candidates_with_excluded_events']+=bool(affected)
            counts[model+'_candidates_with_excluded_pairs']+=bool(affected_pairs)
            counts[model+'_retained_events']+=len(updated['events'])
            original_note=clean[iid]['options'][alias]['witness']
            new_note=anonymize(updated['witness_note']) or '(no retained verification)'
            note_changed=original_note!=new_note
            counts[model+'_witness_note_changed']+=note_changed
            if note_changed:
                changed.append({'id':iid,'model':model,'old':original_note,'new':new_note,
                                'excluded_event_indices':sorted(e['j'] for e in affected),
                                'excluded_paired_event_indices':sorted(e['j'] for e in affected_pairs)})
            clean[iid]['options'][alias]['witness']=new_note
    for name in ['reader.py','common.py']:
        shutil.copyfile(PARENT/name,HERE/name)
    write('strict/reader_inputs.json.gz',clean)
    write('strict/receipts.json.gz',rows)
    write('strict/affected_notes.json',changed)
    write('strict/input_audit.json',dict(counts))
    jobs=[{'issue':iid,'arm':'witness','reverse':reverse} for iid in sorted(clean) for reverse in (False,True)]
    jobs.sort(key=lambda row:sha('schedule4-strict|'+canon(row)))
    write('strict/schedule.json',jobs)
    files=['reader.py','common.py','strict_writer.py','PROTOCOL.md','reader_inputs.json.gz','schedule.json',
           'receipts.json.gz','affected_notes.json','input_audit.json']
    write('strict/input_lock.json',{name:sha((HERE/name).read_bytes()) for name in files})
    print(json.dumps({'assignments':len(jobs),'counts':dict(counts)},indent=2))
if __name__=='__main__':
    main()

