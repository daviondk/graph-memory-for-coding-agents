"""Reconstruct both preregistration receipts; existing registrations must be identical."""
from core42 import D,OFF,R41,read,save,sha


def fixed(name,values):
    p=D/name
    if p.exists():
        assert read(p)==values
    else:
        assert not (D/"forecast-seal.json").exists()
        save(p,values)
    print(name,sha(p))


def main():
    split=read(OFF/"split.json.gz")
    train={r["t"] for r in split["train"]};dev={r["t"] for r in split["dev"]};test={r["t"] for r in split["test"]}
    assert not (train&test or train&dev or test&dev)
    fixed("registration.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),code=sha(D/"features42.py"),
        r41=sha(R41/"manifest.json"),split=sha(OFF/"split.json.gz"),train_t=len(train),
        test_t=len(test),train=len(split["train"]),test=len(split["test"])))
    fixed("supervision-registration.json",dict(protocol=sha(D/"SUPERVISION_RU.md"),
        registered=sha(D/"registration.json"),method=sha(D/"METHOD_RU.md")))


if __name__=="__main__":main()
