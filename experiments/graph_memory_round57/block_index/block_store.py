"""SQLite event index with immediate journal durability and optional deferred postings."""
from collections import Counter, defaultdict
from pathlib import Path
import sqlite3
import sys

R56 = Path(__file__).resolve().parents[2] / "graph_memory_round56"
sys.path.insert(0, str(R56 / "durable"))
from store import best

BLOCK = 64
ALL_BITS = (1 << BLOCK) - 1
HIGH_BIT = 1 << (BLOCK - 1)
MASK_UPSERT = """INSERT INTO posting VALUES(?,?,?)
ON CONFLICT(f,b) DO UPDATE SET mask = posting.mask | excluded.mask"""
BYTE_APPEND = """INSERT INTO posting VALUES(?,?)
ON CONFLICT(f) DO UPDATE SET js=CAST(posting.js || excluded.js AS BLOB)"""
ARMS = ("join", "filelist", "immediate", "sealed")
EXTRA = ("sealed_list", "striped_list")
TAIL_MODES = ("sealed", *EXTRA)
STRIPE = 1024
STRIPE_APPEND = """INSERT INTO posting VALUES(?,?,?)
ON CONFLICT(f,b) DO UPDATE SET js=CAST(posting.js || excluded.js AS BLOB)"""
EVENT = "CREATE TABLE event(j INTEGER PRIMARY KEY,rev BLOB NOT NULL,members BLOB NOT NULL)"
SCHEMAS = {
    "join": "CREATE TABLE posting(f,j,PRIMARY KEY(f,j)) WITHOUT ROWID",
    "filelist": "CREATE TABLE posting(f INTEGER PRIMARY KEY,js BLOB NOT NULL)",
    "immediate": "CREATE TABLE posting(f INTEGER,b INTEGER,mask INTEGER,PRIMARY KEY(f,b)) WITHOUT ROWID",
}
SCHEMAS["sealed"] = SCHEMAS["immediate"]
SCHEMAS["sealed_list"] = SCHEMAS["filelist"]
SCHEMAS["striped_list"] = "CREATE TABLE posting(f INTEGER,b INTEGER,js BLOB NOT NULL,PRIMARY KEY(f,b)) WITHOUT ROWID"


def varints(ids):
    payload = bytearray()
    for value in ids:
        if not isinstance(value, int) or value < 0:
            raise ValueError("invalid unsigned ID")
        while value >= 128:
            payload.append(128 | (value & 127))
            value >>= 7
        payload.append(value)
    return bytes(payload)


def unpack(blob):
    values = []
    value = shift = 0
    for byte in blob:
        value |= (byte & 127) << shift
        if byte < 128:
            values.append(value)
            value = shift = 0
        else:
            shift += 7
    if shift:
        raise ValueError("truncated varint")
    return tuple(values)


def signed(mask):
    return mask if mask < HIGH_BIT else mask - (1 << BLOCK)


class BlockStore:
    def __init__(self, path, mode, create=False):
        if mode not in SCHEMAS:
            raise ValueError(mode)
        self.mode = mode
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL").fetchone()
        self.db.execute("PRAGMA synchronous=FULL")
        if create:
            self.db.execute(EVENT)
            self.db.execute(SCHEMAS[mode])
        self.next_id = self.db.execute("SELECT COALESCE(MAX(j),-1)+1 FROM event").fetchone()[0]
        self.tail = {}
        self.incident = defaultdict(list)
        self.restore_rows = self.restore_payload = 0
        self.metadata_rows = self.metadata_bytes = 0
        if mode in TAIL_MODES:
            boundary = self.next_id - self.next_id % BLOCK
            for j, blob in self.db.execute("SELECT j,members FROM event WHERE j>=? ORDER BY j", (boundary,)):
                self._retain(j, unpack(blob))
                self.restore_rows += 1
                self.restore_payload += len(blob)

    def _retain(self, j, ids):
        self.tail[j] = ids
        for f in ids:
            self.incident[f].append(j)

    def append(self, j, rev, ids, fault=False):
        ids = tuple(ids)
        raw_sha = bytes.fromhex(rev)
        if len(raw_sha) != 20 or len(ids) < 2 or len(ids) != len(set(ids)):
            raise ValueError("invalid event")
        payload = varints(ids)
        if j < self.next_id:
            row = self.db.execute("SELECT rev,members FROM event WHERE j=?", (j,)).fetchone()
            if row != (raw_sha, payload):
                raise ValueError("conflicting replay")
            return False
        if j != self.next_id:
            raise ValueError("event gap")
        seal = self.mode in TAIL_MODES and (j + 1) % BLOCK == 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT INTO event VALUES(?,?,?)", (j, raw_sha, payload))
            if self.mode == "join":
                self.db.executemany("INSERT INTO posting VALUES(?,?)", ((f,j) for f in ids))
            elif self.mode == "filelist":
                pointer = varints((j,))
                self.db.executemany(BYTE_APPEND, ((f,pointer) for f in ids))
            elif self.mode == "immediate":
                bit = signed(1 << (j % BLOCK))
                self.db.executemany(MASK_UPSERT, ((f,j // BLOCK,bit) for f in ids))
            elif seal and self.mode == "sealed":
                masks = {f:sum(1 << (k % BLOCK) for k in events) for f,events in self.incident.items()}
                for f in ids:
                    masks[f] = masks.get(f,0) | HIGH_BIT
                self.db.executemany("INSERT INTO posting VALUES(?,?,?)",
                                    ((f,j // BLOCK,signed(bits)) for f,bits in masks.items()))
            elif seal:
                stripe = j // STRIPE
                is_striped = self.mode == "striped_list"
                base = stripe * STRIPE if is_striped else 0
                packets = {f:varints(k-base for k in events) for f,events in self.incident.items()}
                newest = varints((j-base,))
                for f in ids:
                    packets[f] = packets.get(f,b"") + newest
                if is_striped:
                    self.db.executemany(STRIPE_APPEND, ((f,stripe,pkt) for f,pkt in packets.items()))
                else:
                    self.db.executemany(BYTE_APPEND, packets.items())
            if fault:
                raise RuntimeError("injected rollback")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        if self.mode in TAIL_MODES:
            if seal:
                self.tail.clear()
                self.incident.clear()
            else:
                self._retain(j, ids)
        self.next_id += 1
        return True

    def _fetch_events(self, ids):
        chunks = []
        n = 0
        for start in range(0,len(ids),400):
            keys = ids[start:start+400]
            placeholders = ",".join("?" for _ in keys)
            command = "SELECT members FROM event WHERE j IN (" + placeholders + ")"
            chunks.extend(self.db.execute(command, keys))
            n += 1
        return chunks,n

    def read(self, f, tie, prior):
        counts = Counter()
        calls = 1
        if self.mode == "join":
            rows = self.db.execute("SELECT e.members FROM posting p JOIN event e ON p.j=e.j WHERE p.f=?",
                                   (f,)).fetchall()
        else:
            ids = []
            if self.mode in ("filelist","sealed_list"):
                row = self.db.execute("SELECT js FROM posting WHERE f=?", (f,)).fetchone()
                if row:
                    ids.extend(unpack(row[0]))
                    self.metadata_rows += 1
                    self.metadata_bytes += len(row[0])
            elif self.mode == "striped_list":
                for stripe, blob in self.db.execute("SELECT b,js FROM posting WHERE f=?", (f,)):
                    self.metadata_rows += 1
                    self.metadata_bytes += 8 + len(blob)
                    ids.extend(stripe*STRIPE + k for k in unpack(blob))
            else:
                pages = self.db.execute("SELECT b,mask FROM posting WHERE f=?", (f,)).fetchall()
                self.metadata_rows += len(pages)
                # Logical fixed-width request payload: a 64-bit block ID and 64-bit mask.
                self.metadata_bytes += 16 * len(pages)
                for page, mask in pages:
                    mask &= ALL_BITS
                    while mask:
                        low = mask & -mask
                        ids.append(page * BLOCK + low.bit_length() - 1)
                        mask -= low
            for j in self.incident.get(f, ()):
                counts.update(self.tail[j])
            rows, n = self._fetch_events(ids)
            calls += n
        nbytes = 0
        for (blob,) in rows:
            nbytes += len(blob)
            counts.update(unpack(blob))
        return best(counts, f, tie, prior), (calls, len(rows), nbytes)

    def close(self):
        self.db.close()
