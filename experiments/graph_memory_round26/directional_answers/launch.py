"""Retry the same atomic write when a Windows reader briefly holds the status path."""
import time
import infer
from prepare import D,P,Path,sha,save
def robust(path,obj):
    for wait in (.02,.05,.10,.25,.50,1.,2.,4.):
        try:return save(path,obj)
        except PermissionError as exc:
            if getattr(exc,"winerror",None) not in (5,32):raise
            time.sleep(wait)
    return save(path,obj)
if __name__=="__main__":
    robust(D/"runtime-note.json",dict(issue="temporary Windows sharing violation while replacing progress.json; same sealed contexts, cache and model",resolved_by=sha(Path(__file__)),
        same_inference=sha(D/"infer.py"),same_input_seal=sha(D/"input-lock.json")))
    infer.save=robust
    infer.main()
