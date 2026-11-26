from io43 import D,OFF,R41,R42,read,sha,save


def main():
    r=dict(protocol=sha(D/"PROTOCOL_RU.md"),gate=sha(D/"trigger43.py"),forecast=sha(D/"forecast43.py"),
        r42=sha(R42/"manifest.json"),weights=sha(R42/"models.json"),r41=sha(R41/"manifest.json"),
        split=sha(OFF/"split.json.gz"),threshold=8)
    p=D/"registration.json"
    if p.exists():assert read(p)==r
    else:
        assert not (D/"forecast-0-seal.json").exists()
        save(p,r)
    print(sha(p))


if __name__=="__main__":main()
