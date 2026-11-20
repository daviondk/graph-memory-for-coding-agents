"""Materialize common historical observations, query addresses, separate answers and the frozen graph readouts."""
from pathlib import Path
from collections import defaultdict
from hashlib import sha256
import base64
import gzip
import json
import re
import sys

HERE = Path(__file__).resolve().parent
R5 = HERE.parents[1] / 'graph_memory_round5'
DATA = R5 / 'action_transfer'
sys.path.insert(0, str(DATA))
import replicate as r5


def rows(path):
    with gzip.open(path, 'rt', encoding='utf8') as fp:
        yield from map(json.loads, fp)


def emit(fp, row):
    fp.write(json.dumps(row, ensure_ascii=True, separators=(',', ':')) + '\n')


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def stable(obj):
    return sha256(json.dumps(obj, ensure_ascii=True).encode()).hexdigest()


def matched_inputs(task, terminal):
    cwd = True
    projected = []
    rev = 0
    path_version = {}
    for step, (ev, extra) in enumerate(zip(task['events'], terminal, strict=True), 1):
        name, args, text = ev
        p = r5.anchor.rel(args.get('path'))
        cmd = args.get('command', '')
        change = bool(p and (r5.anchor.success(cmd, p, text) or cmd in ('insert', 'create', 'undo_edit')))
        if change:
            rev += 1
            path_version[p] = rev
        seen = defaultdict(dict)
        if name in ('str_replace_editor', 'str_replace_based_edit_tool', 'edit_file') and p:
            seen[p].update(r5.anchor.printed(text))
        for path, n, line, _ in r5.pol.readlines(extra, cwd):
            seen[path][n] = line
        if extra:
            command = extra['command']
            if re.search(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b', command):
                cwd = False
            if re.fullmatch(r'\s*cd\s+/testbed/?\s*', command):
                cwd = True
        files = {path: [[ns[0], [lines[n] for n in ns]] for ns in r5.anchor.groups(lines)]
                 for path, lines in seen.items() if lines}
        projected.append(dict(step=step, rev=rev, changed=p if change else None, files=files))
    return projected


def prepare():
    seals = json.loads((DATA / 'decisions_lock.json').read_text())
    raw_seal = json.loads((DATA / 'sources_lock.json').read_text())
    names = [f'{kind}_{k}.gz' for k in range(8) for kind in ('bounded_cuts', 'source', 'terminal')]
    for name in names:
        assert sha(DATA / name) == (seals['files'] | raw_seal['data'])[name]
    with (gzip.open(HERE / 'stream.jsonl.gz', 'wt', encoding='utf8') as streams,
          gzip.open(HERE / 'queries.jsonl.gz', 'wt', encoding='utf8') as queries,
          gzip.open(HERE / 'answers.jsonl.gz', 'wt', encoding='utf8') as gold,
          gzip.open(HERE / 'graph.jsonl.gz', 'wt', encoding='utf8') as predictions):
        for k in range(8):
            cuts = iter(rows(DATA / f'bounded_cuts_{k}.gz'))
            pairs = rows(DATA / f'terminal_{k}.gz')
            for task, (iid, terminal) in zip(rows(DATA / f'source_{k}.gz'), pairs, strict=True):
                assert iid == task['instance']
                events = matched_inputs(task, terminal)
                emit(streams, dict(id=iid, repo=task['official_repo'], events=events))
                cut_blobs = {}
                candidates = []
                tasks = []
                for t in range(4, len(events), 4):
                    ci, ct, arms = next(cuts)
                    assert (ci, ct) == (iid, t)
                    cut_blobs[t] = arms
                    args, output = r5.anchor.future_check(task['events'], t)
                    if args:
                        p = r5.anchor.rel(args.get('path'))
                        if r5.anchor.success(args.get('command'), p, output):
                            inverted = r5.anchor.invert(args, output)
                            if inverted:
                                lo, lines = inverted
                                tasks.append(('edit', t, p, lo, lines, None))
                    # Positive control. One reproducible, previously observed, 3-line
                    # span per eligible task. The observation precedes the query and
                    # lies at the same visible repository revision. No future data.
                    recent = {}
                    for ev in reversed(events[:t]):
                        if ev['rev'] != events[t-1]['rev']:
                            break
                        for path, spans in ev['files'].items():
                            if path in recent:
                                continue
                            recent[path] = True
                            if ev['step'] == t:
                                continue
                            for start, observed in spans:
                                if len(observed) < 3:
                                    continue
                                half = (len(observed)-3)//2
                                ls = observed[half:half+3]
                                if not any(len(re.sub(r'\W', '', s)) >= 8 for s in ls):
                                    continue
                                entry = ('control', t, path, start+half, ls, ev['step'])
                                candidates.append((stable([iid,t,path,start+half,ev['step']]), entry))
                if candidates:
                    tasks.append(min(candidates, key=lambda v:v[0])[1])
                for kind,t,p,lo,lines,source in tasks:
                    key = f'{iid}/{t}/{kind}'
                    emit(queries, dict(key=key,id=iid,repo=task['official_repo'],kind=kind,t=t,
                                       path=p,lo=lo,n=len(lines),source=source))
                    emit(gold, [key, lines])
                    predicted = {}
                    for name in ('address','base','lru_address'):
                        state = base64.b64decode(cut_blobs[t][name])
                        decoded = r5.bound.decode(state[1:])
                        assert len(state) <= 4096 and decoded[1] == t
                        table = r5.bound.prior.materialize(decoded)[1]['rebase'].get(p,{})
                        predicted[name] = [table.get(n, (None,))[0] for n in range(lo,lo+len(lines))]
                    emit(predictions,[key,predicted])
            assert next(cuts, None) is None
    print('projected', {n:sum(1 for _ in rows(HERE/n)) for n in ('stream.jsonl.gz','queries.jsonl.gz','answers.jsonl.gz','graph.jsonl.gz')})


if __name__ == '__main__':
    prepare()
