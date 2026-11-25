"""Independent descriptive audit. Does not read forecasts, embeddings or scores."""
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
from tempfile import TemporaryDirectory

import prepare

D = Path(__file__).resolve().parent
SOURCE = prepare.SOURCE
WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def family(doc):
    stem, suffix = doc.rsplit("_", 1)
    assert stem.isdigit() and re.fullmatch(r"(?:\d+|m\d*)", suffix)
    return stem


def distr(values):
    return dict(sorted(collections.Counter(values).items()))


def coverage(rows, packets):
    panels = {'exact': collections.Counter(), 'casefold': collections.Counter()}
    totals = collections.Counter()
    lengths = []
    incidents = {mode: collections.Counter() for mode in panels}
    repeat_refs = collections.defaultdict(list)
    panels_by_fam = {mode: set() for mode in panels}
    one_block_multiplicity = collections.Counter()
    per_family_covered = collections.Counter()
    covered_cases = []
    for packet in packets:
        doc, anchor = packet['id'], packet['anchor']
        literal = rows[doc].get('ref sentences')
        if literal is None:
            totals['missing_ref_field'] += 1
            continue
        if isinstance(literal,str):
            totals['scalar_string_fields'] += 1
            literal = [literal]
        else:
            assert isinstance(literal,list)
        refs_raw = [prepare.norm(v) for v in literal]
        totals['annotated_rows'] += 1
        totals['duplicate_refs_within_row'] += len(refs_raw)-len(set(refs_raw))
        totals['empty_ref_entries'] += sum(not x for x in refs_raw)
        refs = list(dict.fromkeys(v for v in refs_raw if v))
        for ref in refs:
            words=len(WORDS.findall(ref)); lengths.append(words)
            repeat_refs[ref].append((doc, family(doc)))
            for bound in (1, 3, 5, 10):
                if words<=bound:totals[f'references_at_most_{bound}_words'] += 1
        totals['rows_with_multiple_distinct_references'] += int(len(refs)>1)
        for mode in panels:
            norm = (lambda x:x) if mode=='exact' else str.casefold
            target=[norm(v) for v in refs]
            entries=[(i,norm(v)) for i,v in packet['records']]
            parts=dict(entries); concat=norm(prepare.norm(' '.join(parts.values())))
            orig=norm(prepare.norm(rows[doc]['text'])); first=norm(anchor)
            sets=[]
            for ref, raw_text in zip(target, refs):
                found={i for i,v in entries if ref in v}
                sets.append(found)
                inc=incidents[mode]
                inc['total_nonempty_distinct_within_row_references'] += 1
                inc['in_original_text'] += int(ref in orig)
                inc['in_donated_anchor'] += int(ref in first)
                inc['in_remaining_concatenated_text'] += int(ref in concat)
                inc['inside_one_returned_record'] += int(bool(found))
                inc['inside_multiple_distinct_records'] += int(len(found)>1)
                if found:
                    inc['one_or_more_matches_entire_record'] += int(any(ref==parts[i] for i in found))
                    inc['matches_only_as_substring'] += int(all(ref!=parts[i] for i in found))
                    inc['multiple_occurrences_anywhere_within_records'] += int(sum(parts[i].count(ref) for i in found)>1)
                if mode=='exact':
                    one_block_multiplicity[len(found)] += 1
            z=panels[mode]
            if any(sets): category='at_least_one_block'
            else:
                halves=orig.split(first)
                parts_native=[prepare.norm(s) for s in halves]
                if any(v in part for v in target for part in parts_native):
                    category='remaining_text_same_side_but_crosses_a_block_boundary'
                elif any(v in first for v in target):
                    category='only_in_anchor_or_crosses_its_boundary'
                elif any(v in orig for v in target):
                    category='crosses_anchor_boundary'
                else:
                    category='no_verbatim_ref_anywhere_in_full_text'
            z['partition_'+category]+=1
            hit=any(sets); any_short=any(s and len(WORDS.findall(v))<=3 for s,v in zip(sets,refs))
            z['rows_any_reference_in_single_record'] += int(hit)
            z['all_references_separately_coverable'] += int(bool(refs) and all(sets))
            z['all_references_jointly_in_one_record'] += int(bool(sets) and bool(set.intersection(*sets)))
            z['rows_have_multiple_matching_record_choices'] += int(bool(sets) and len(set.union(*sets))>1)
            z['rows_at_least_one_coverable_short_ref_3_words'] += int(any_short)
            z['rows_all_coverable_refs_short_3_words'] += int(hit and all(len(WORDS.findall(v))<=3 for s,v in zip(sets,refs) if s))
            z['rows_entirely_unmatched_in_original'] += int(not any(v in orig for v in target))
            z['rows_any_ref_in_donated_anchor'] += int(any(v in first for v in target))
            if any(sets):
                panels_by_fam[mode].add(family(doc))
                if mode=='exact':
                    covered_cases.append(doc)
                    per_family_covered[family(doc)]+=1
    for mode,f in panels_by_fam.items():panels[mode]['eligible_families']=len(f)
    repeated=[v for v in repeat_refs.values() if len(v)>1]
    cross=[v for v in repeated if len({f for d,f in v})>1]
    return (dict(fields=totals,row_coverage=panels,reference_coverage=incidents,
                 matching_records_per_reference_exact=one_block_multiplicity,
                 word_counts=dict(median=statistics.median(lengths),min=min(lengths),max=max(lengths)),
                 exact_reference_reuse=dict(distinct=len(repeat_refs),texts_reused_in_multiple_rows=len(repeated),
                                           texts_reused_across_families=len(cross)),
                 eligible_cases_by_family_size=distr(per_family_covered.values())), set(covered_cases))


def similarity(rows, eligible):
    docs=sorted(rows); q=[family(d) for d in docs]
    full=[prepare.norm(rows[d]['text']) for d in docs]
    backgrounds=[prepare.norm(s.replace(prepare.norm(rows[d]['evidence']),'')) for d,s in zip(docs,full)]
    grouped=collections.defaultdict(list)
    for i,x in enumerate(backgrounds):grouped[x].append(i)
    groups=[v for v in grouped.values() if len(v)>1]
    def signature(t):
        words=WORDS.findall(t.casefold())
        return {tuple(words[j:j+7]) for j in range(max(0,len(words)-6))}
    # Independent shingle resemblance. Only positive rows enter the primary comparisons.
    inv=collections.defaultdict(list)
    sizes=[]
    for i,bg in enumerate(backgrounds):
        terms=signature(bg);sizes.append(len(terms))
        for term in terms:inv[term].append(i)
    intersection=collections.Counter()
    for ids in inv.values():
        for i,j in itertools.combinations(ids,2):intersection[i,j]+=1
    pairs_all=list(itertools.combinations(range(len(docs)),2))
    thresholds={0.8:collections.Counter(),0.9:collections.Counter(),0.95:collections.Counter()}
    respective_groups={}
    mapping90={}
    for th in thresholds:
        parents={f:f for f in q}
        def root(f):
            while parents[f]!=f:
                parents[f]=parents[parents[f]]
                f=parents[f]
            return f
        connected=set()
        for i,j in pairs_all:
            same=q[i]==q[j]
            count=intersection[i,j]
            union=sizes[i]+sizes[j]-count
            if count>=th*union and union>0:
                k='same_family' if same else 'different_families'
                thresholds[th][k]+=1
                if not same:
                    connected.add(tuple(sorted((q[i],q[j]))))
                    parents[root(q[i])]=root(q[j])
        thresholds[th]['distinct_interfamily_links']=len(connected)
        thresholds[th]['total_within_family_pairs']=sum(q[i]==q[j] for i,j in pairs_all)
        thresholds[th]['total_across_family_pairs']=len(pairs_all)-thresholds[th]['total_within_family_pairs']
        if th==0.9:
            hashed={f:hashlib.sha256(('contradoc-family-v1|'+f).encode('ascii')).hexdigest()[:16] for f in set(q)}
            assert len(set(hashed.values()))==len(hashed)
            components=collections.defaultdict(list)
            for f in set(q):components[root(f)].append(hashed[f])
            mapping90={hashed[f]:'C'+min(components[root(f)]) for f in set(q)}
        respective_groups[th]=dict(all=len({root(f) for f in q}),
                                    primary=len({root(family(doc)) for doc in eligible}))
    def repeated(txt):
        arr=collections.defaultdict(list)
        for i,v in enumerate(txt):arr[v].append(i)
        return dict(distinct=len(arr),within_same_family_pairs=sum(q[i]==q[j] for g in arr.values() for i,j in itertools.combinations(g,2)),
                    distinct_families_pairs=sum(q[i]!=q[j] for g in arr.values() for i,j in itertools.combinations(g,2)))
    return dict(full_text=repeated(full),anchor_removed_text=repeated(backgrounds),
                map_jaccard90=mapping90,
                map_key_definition="SHA256(ASCII('contradoc-family-v1|' + ID before final underscore)) first 16 lowercase hex. Component = C + minimum pseudonym in connected component.",
                seven_word_shingle_comparison=thresholds,connected_component_count_after_interfamily_merges=respective_groups,
                distinct_families_per_doc_type={tp:len({family(d) for d,r in rows.items() if r['doc_type']==tp}) for tp in sorted({r['doc_type'] for r in rows.values()})},
                families_mixing_document_genres=sum(len({rows[docs[i]]['doc_type'] for i,f2 in enumerate(q) if f==f2})>1 for f in set(q)))


def main():
    src=SOURCE.read_bytes(); assert prepare.sha(src)==prepare.SOURCE_SHA
    pos=prepare.read(SOURCE)['pos']; assert all(d==r['unique id'] for d,r in pos.items())
    full,reasons1=prepare.build(pos)
    stripped={d:{k:r[k] for k in ('text','evidence')} for d,r in pos.items()}
    packets,reasons2=prepare.build(stripped)
    assert full==packets and reasons1==reasons2
    lock=prepare.read(D/'input-lock.json')
    with TemporaryDirectory(dir=prepare.CACHE) as temp:
        dest=Path(temp)/'blind.json.gz'
        prepare.dump(dest,packets)
        digest=prepare.sha(dest.read_bytes());assert digest==lock['packets']
        assert dest.read_bytes()==(prepare.CACHE/'packets.json.gz').read_bytes()
    coverage_report,eligible=coverage(pos,packets)
    by_family=collections.Counter(family(d) for d in pos)
    out=dict(source=prepare.SOURCE_SHA,input_packets=digest,source_code_sha256=prepare.sha((D/'prepare.py').read_bytes()),
             audit_code_sha256=prepare.sha(Path(__file__).read_bytes()),rows=len(pos),negative_rows_outside_endpoint=len(json.loads(src)['neg']),
             family_count=len(by_family),rows_per_family_distribution=distr(by_family.values()),
             field_stripping_byte_identical=True,excluded_at_preparation=len(reasons2),
             note='Reference fields are used only in this audit. No scores, predictions or models are read.',
             availability=coverage_report,document_reuse=similarity(pos,eligible))
    prepare.dump(D/'data-audit.json',out)
    print(json.dumps(out,ensure_ascii=True,indent=2))
if __name__=='__main__': main()
