from acquire import D,save,h
roots=['sota_round/swe_context/reference-audit.md','memory_session5/literature/summary_ru.md']
work=D.parents[1]
evidence=[]
for name in roots:
    p=work/name
    evidence.append({"path":str(p),"sha":h(p.read_bytes()),"matching_lines":[i+1 for i,line in enumerate(p.read_text(encoding="utf8").splitlines()) if "2608.00808" in line]})
save('local_history.json',{"search":"arXiv 2608.00808, Wang and Ledger, govern/inform; inspected earlier research workspace, shared tracking repo and archived reports on D","located":evidence,"outcome":"Earlier reports identify external author figures; no verified local author runtime in examined roots."})
