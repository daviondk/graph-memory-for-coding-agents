"""Only these small, deterministic public API commands are observed."""
from sources import ROOT,canon,save,sha
import re
def cases():
    out=[]
    def group(pkg,mod,fn,examples,fmt='plain'):
        for args,kwargs in examples:out.append({'pkg':pkg,'module':mod,'function':fn,'args':args,'kwargs':kwargs,'format':fmt})
    def arg(xs):return [([x],{}) for x in xs]
    versions=['1','1.0.0','1!2.0rc1.post1.dev2+ABC.3','v1.0','1.2.3beta4','2.0-1','1.0.dev0','01.002','1.0alpha','1.0+foo-y','1.*','legacy','2024.01.0','1.0preview2','2.0post','1.0+ä','  1.2  ','1.2.dev']
    group('packaging','version','Version',arg(versions),'str')
    group('packaging','utils','canonicalize_version',arg(versions),'str')
    group('packaging','utils','canonicalize_name',arg(['Some_Pkg.X','hello--World','bad...Name','-name','a','x_2','Hello 1','my.pkg']),'str')
    group('packaging','specifiers','SpecifierSet',arg(['>=1,<2','==1.*','<=1.0rc1','===anything','==1.0+abc','~=1.2.3','>=2.*','!=1.0.*','>=1.2.*','>1.0+local','!=1.2+vendor','==1.0.*.3','==1.2a1.*','~=1.0.dev1','==1!2.0']),'str')
    group('packaging','requirements','Requirement',arg(['foo','foo[bar,qux]>=1.0','Name @ https://x.test/a','foo>=2.*','foo; python_version > "3.10"','x @ git+ssh://host/xyz','X @ path','X @ ./file.whl','X @ file:foo','foo (>=1,<2)','foo=2','bad[','Foo>=1; os.name=="posix"','foo @ https://x.test ; python_version < "3.9"']),'str')
    group('packaging','utils','parse_wheel_filename',arg(['ok-1.0-py3-none-any.whl','my_pkg-2.0-1a-cp310-cp310-win_amd64.whl','x-bad-py3-none-any.whl','foo.whl','x-1.0-1@-py3-none-any.whl','pkg-1.0-py2.py3-none-any.whl']),'wheel')
    labels=['example.com','faß.de','straße.de','xn--fa-hia.de','Σίσυφος.gr','bücher.example','e\u0301.fr','a_b.example','a..b','ABC.DE','a\u200db','βόλος.gr','ＡＢＣ．ｃｏｍ','💩.la','😀.example','☕.com','İstanbul.com','\u00adfoo.de','a'*64+'.com','a。b','\u0378.example','l·l.cat','域名.测试','אבג.example','K.example','\u1c89.example','\U00011f02.example','\U0001FAE8.example','\U00010570.example','\U00010E80.example']
    for fn in ['encode','decode']:
        group('idna','',fn,[([s],kw) for s in labels for kw in [{},{'uts46':True},{'uts46':True,'std3_rules':True}]],'bytes_or_value')
    chars=[0,7,32,65,0xad,0x300,0x34f,0x903,0x1100,0x1160,0x200b,0x200d,0x231a,0x2600,0x2708,0xff00,0xfe0f,0x1f600,0x1f972,0x1f979,0x1fae0,0x1fae8,0x1fae9,0x1fa70,0x1fa90,0x1fa95,0x1fac0,0x1faf6,0x11f02,0x10570,0x10e80,0x1cc00,0xe0100]
    group('wcwidth','','wcwidth',arg([chr(n) for n in chars]))
    strings=['A','ab','A\u0301','\x07X','👩\u200d💻','☕️','\u2708\ufe0f','\ufe0f','A\u200dB','🏳️\u200d🌈','👨\u200d👩\u200d👧','☀️a','0️⃣','😶\u200d🌫️','🇨🇦','\u0300a','A\ufe0f','\u200dA','❤\ufe0f','🌐','']
    group('wcwidth','','wcswidth',arg(strings))
    seqs=[[],[0],[1,2,3],[0,1,1,2],[2,0,3,0,2,1],[1]*6,list(range(9))];pkg='more_itertools'
    for f in ['chunked','windowed','grouper','batched','sliding_window','ichunked','distribute','divide']:
        group(pkg,'',f,[([n,s] if f in ['distribute','divide'] else [s,n],{}) for s in seqs for n in [0,1,2,4]],'seq')
    for f in ['unique_everseen','unique_justseen','run_length','collapse','powerset','distinct_permutations','all_equal','first','last','one','only','exactly_n','count_cycle','pairwise','triplewise']:
        if f=='count_cycle':continue
        group(pkg,'',f,[([s,2] if f=='exactly_n' else [s],{}) for s in seqs[:5]],'seq')
    for r in out:r['key']=sha(canon(r).encode())[:18]
    assert len(out)==len({r['key'] for r in out})
    return out
if __name__=='__main__':save(ROOT/'roster.json',cases());print(len(cases()))

