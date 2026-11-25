from store import *
if __name__=='__main__':
    lock();path=D/'analysis-lock.json';rec={'files':{name:sha(D/name) for name in ['plan.json','db-receipt.json','reader.py','score.py','store.py','PROTOCOL_RU.md']},'selector_equal_to_r25':True,'primary':'ISETrace gap-minus-window, exactly matched supplemental read tokens; full support','transfer':'MultiDoc2Dial; same parameters, sentences instead of lines','test_labels_opened':False}
    if path.exists():assert read(path)==rec
    else:assert not any(D.glob('*-forecasts.json.gz'));save(path,rec)
