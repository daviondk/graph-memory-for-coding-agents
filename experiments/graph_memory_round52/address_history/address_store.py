"""Minimal SQLite history for address-only and address-plus-score reads."""
from engine import setup,statement

HIST_INIT="""
CREATE TABLE history(q INT NOT NULL,step INT NOT NULL,id INT NOT NULL,
                     PRIMARY KEY(q,step)) WITHOUT ROWID;
INSERT INTO history SELECT q,0,id FROM (
 SELECT q,id,ROW_NUMBER() OVER(PARTITION BY q ORDER BY b DESC,r,id) AS pos FROM c
) WHERE pos=1;
"""
PROMOTE="""
CREATE TRIGGER promote AFTER UPDATE OF seen ON c WHEN OLD.seen IS NULL AND NEW.seen IS NOT NULL BEGIN
 INSERT OR REPLACE INTO history
 SELECT NEW.q,NEW.seen,NEW.id FROM (
   SELECT incumbent.id,incumbent.r,
          CASE WHEN incumbent.seen IS NULL OR incumbent.id=NEW.id THEN incumbent.b ELSE incumbent.u END AS score
   FROM c AS incumbent WHERE incumbent.q=NEW.q AND incumbent.id=(
     SELECT id FROM history WHERE q=NEW.q ORDER BY step DESC LIMIT 1
   )
 ) WHERE {allowed} AND (NEW.u>score OR (NEW.u=score AND (NEW.r,NEW.id)<(r,id)));
END;
"""
REMOVE_TRANSIENT="""
CREATE TRIGGER coalesce_id AFTER UPDATE OF upto ON cursor WHEN NEW.upto>OLD.upto BEGIN
 DELETE FROM history WHERE q=NEW.q AND step=NEW.upto AND id=(
   SELECT id FROM history WHERE q=NEW.q AND step<NEW.upto ORDER BY step DESC LIMIT 1
 );
END;
"""

def plan_setup(db,name):
    if name not in ("thin","address"):return setup(db,name)
    allowed="NEW.id<>id" if name=="address" else "1"
    ddl=HIST_INIT+PROMOTE.format(allowed=allowed)+(REMOVE_TRANSIENT if name=="address" else "")
    db.executescript("BEGIN;"+ddl+"COMMIT;")

def read_pair(name):
    if name=="journal":return "SELECT id,score FROM history WHERE q=?1 AND step<=?2 ORDER BY step DESC LIMIT 1"
    if name in ("thin","address"):
        addr="SELECT id FROM history WHERE q=?1 AND step<=?2 ORDER BY step DESC LIMIT 1"
    else:addr=statement(name,False)
    return "SELECT id,CASE WHEN seen<=?2 THEN u ELSE b END FROM c WHERE q=?1 AND id=("+addr+")"

