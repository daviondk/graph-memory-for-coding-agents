"""Certified relocation of the exact source bytes after a single authenticated replacement."""
import hashlib
import hmac
import json

TEST_AUTHORITY = b"public synthetic test authority; accepts no production inputs"


def canonical(obj):
    return json.dumps(obj,ensure_ascii=True,separators=(",",":"),sort_keys=True).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def attest(obj):
    return {"fields": obj, "tag": hmac.new(TEST_AUTHORITY,canonical(obj),"sha256").hexdigest()}


def authentic(receipt):
    return (isinstance(receipt,dict) and set(receipt)=={"fields","tag"} and isinstance(receipt["tag"],str)
            and hmac.compare_digest(attest(receipt["fields"])["tag"],receipt["tag"]))


def move_span(lo,hi,start,end,insert_size):
    if hi <= start:
        return lo,hi
    if lo >= end:
        delta=insert_size-(end-start)
        return lo+delta,hi+delta
    return None


def transfer(observed, earlier, edit, target):
    if not authentic(earlier):
        return "source_signature",None
    if not authentic(edit):
        return "edit_absent_or_signature",None
    old,delta=earlier["fields"],edit["fields"]
    if (old["path"],old["rev"],old["root"])!=(delta["path"],delta["before"],delta["old_root"]):
        return "source_parent",None
    if (delta["path"],delta["after"],delta["new_root"])!=target:
        return "target_identity",None
    if (len(observed)!=old["hi"]-old["lo"] or digest(observed)!=old["digest"]):
        return "source_bytes",None
    if not (0<=old["lo"]<old["hi"]<=delta["old_size"] and
            0<=delta["start"]<=delta["end"]<=delta["old_size"] and delta["insert_size"]>=0 and
            delta["new_size"]==delta["old_size"]-delta["end"]+delta["start"]+delta["insert_size"]):
        return "bounds",None
    dest=move_span(old["lo"],old["hi"],delta["start"],delta["end"],delta["insert_size"])
    if dest is None:
        return "overlap",None
    lo,hi=dest
    assert 0<=lo<hi<=delta["new_size"]
    return "accepted",{"lo":lo,"hi":hi,"digest":old["digest"],"body":observed.decode("ascii"),
                       "source_event":old["event"],"edit_event":delta["event"],
                       "prior_receipt":digest(canonical(earlier)),"edit_receipt":digest(canonical(edit)),
                       "record_kind":"span_certificate","for_root":delta["new_root"]}


def exhaustive():
    counter={"comparisons":0,"accepted":0,"overlap":0,"wrong_bytes":0}
    for n in range(1,13):
        before=bytes(range(n))
        for lo in range(n):
            for hi in range(lo+1,n+1):
                for a in range(n+1):
                    for b in range(a,n+1):
                        for prefix in (b"",b"Q",b"xyz"):
                            after=before[:a]+prefix+before[b:]
                            counter["comparisons"]+=1
                            result=move_span(lo,hi,a,b,len(prefix))
                            if result is None:
                                counter["overlap"]+=1
                            else:
                                counter["accepted"]+=1
                                x,y=result
                                counter["wrong_bytes"]+=int(before[lo:hi]!=after[x:y])
    assert not counter["wrong_bytes"]
    return counter

