"""Post-primary sensitivity. Up to eight historical native reads, newest source for each requested address."""
from pathlib import Path
from collections import Counter
import gzip
import json
import sys

import native
from memtrace.contracts import RecallIntent, RecallTemporalScope
from hashlib import sha256


def retrieve_many(reader,milestone,repo,q,current,directory,has_any_page):
    low=q['lo']
    high=low+q['n']-1
    owners={}
    selected={}
    for candidate in reversed(directory.get(q['path'],[])):
        for first,last in candidate['ranges']:
            for n in range(max(first,low),min(last,high)+1):
                if n not in owners:
                    owners[n]=candidate['step']
                    selected[candidate['step']]=candidate
    order=sorted(Counter(owners.values()).items(),key=lambda it:(-it[1],-it[0]))
    reads=[]
    budget=32768
    npage=8
    for step,_ in order:
        if budget<256 or npage<=0:
            break
        entry=selected[step]
        ids=tuple(entry['pages'][:npage])
        r=RecallIntent(recall_id=q['key']+'/multiple/'+str(step),repository_id=repo,run_id='run-1',
                       branch_id='main',revision_id=entry['rev'],current_milestone_id=milestone,
                       question=f"Recover observed code from {q['path']}, lines {low} to {high}, before editing.",
                       entity_refs=('file:'+q['path'],),temporal_scope=RecallTemporalScope.HISTORICAL_EXECUTION,
                       required_evidence=(),source_memory_ref='memoryref_'+sha256('/'.join(ids).encode()).hexdigest()[:24],
                       direct_page_ids=ids,max_tokens=budget,max_slice_tokens=budget,max_pages=npage)
        out=reader.fault(r)
        used=out.block.token_count
        opens=len(out.trace.pages_read)
        assert used<=budget and opens<=npage
        budget-=used
        npage-=max(1,opens)
        reads.append(dict(step=step,rendered=out.block.rendered_content,opened=opens,tokens=used,
                          status=out.block.coverage.state.value))
    return dict(owners=owners,reads=reads,spent_tokens=32768-budget)


def main():
    native.retrieve=retrieve_many
    native.main()


if __name__=='__main__':
    main()
