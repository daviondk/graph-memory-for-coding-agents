"""Deterministic synthetic producer and an independent byte oracle."""
from certificate import attest,digest

POSITIVE=("after","before_grow","before_shrink","left_insert","right_insert")
NEGATIVE=("changed_inside","equal_inside","damaged_read","wrong_read_path","wrong_old_root",
          "wrong_base","wrong_target","wrong_edit_path","bad_edit_tag","no_edit")


def fixture(name,size):
    path="file:sample"
    old=("".join(chr(65 + (i*17+i//7)%26) for i in range(size+256))).encode()
    lo=64;hi=lo+size;a,b,insert=hi+6,hi+10,b"extension"
    if name=="before_grow":a,b,insert=7,9,b"longer-insertion"
    if name=="before_shrink":a,b,insert=7,22,b"x"
    if name=="left_insert":a,b,insert=lo,lo,b"left"
    if name=="right_insert":a,b,insert=hi,hi,b"right"
    if name=="changed_inside":a,b,insert=lo+4,lo+9,b"12345"
    if name=="equal_inside":a,b,insert=lo+4,lo+9,old[lo+4:lo+9]
    new=old[:a]+insert+old[b:]
    expected_lo=lo + (len(insert)-b+a if b<=lo else 0)
    oldbody=old[lo:hi]
    read=dict(path=path,rev="old",root=digest(old),lo=lo,hi=hi,digest=digest(oldbody),event="source-observation")
    edit=dict(path=path,before="old",after="new",old_root=digest(old),new_root=digest(new),
              start=a,end=b,insert_size=len(insert),old_size=len(old),new_size=len(new),event="edit")
    if name=="wrong_read_path": read["path"]="file:unrelated"
    if name=="wrong_old_root":read["root"]="0"*64
    if name=="wrong_base":edit["before"]="other-parent"
    if name=="wrong_target":edit["after"]="other-target"
    if name=="wrong_edit_path":edit["path"]="file:unrelated"
    oldcert=attest(read);receipt=attest(edit)
    if name=="bad_edit_tag":receipt["tag"]="0"*64
    if name=="no_edit":receipt=None
    if name=="damaged_read":oldbody=b"!"+oldbody[1:]
    return dict(observed=oldbody,read=oldcert,edit=receipt,target=(path,"new",digest(new)),
                oracle_start=expected_lo,oracle_bytes=new[expected_lo:expected_lo+size],size=size,
                expected=name in POSITIVE)

