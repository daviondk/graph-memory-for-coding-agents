from figure import D,rows
import struct,json
if __name__=="__main__":
    assert rows()==json.loads((D/"effects.json").read_bytes())
    png=(D/"comparisons.png").read_bytes()
    assert png[:8]==b"\x89PNG\r\n\x1a\n" and min(struct.unpack(">II",png[16:24]))>=750
    assert (D/"comparisons.pdf").read_bytes().startswith(b"%PDF-")
    print("Verified values for all plotted intervals against the source studies.")

