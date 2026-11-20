from sources import ROOT,canon,save,sha
def cases():
    rows=[]
    def add(pkg,mod,fn,arglist,method='plain'):
        for a,kw in arglist:
            rows.append({'pkg':pkg,'module':mod,'function':fn,'args':a,'kwargs':kw,'format':method})
    tomls=['','a=1','a=true','a="hello"','a="""abc"""','a={ k=1, y=2 }','a={foo=1,}','a=01','a=+01','a=0xff','a=0b101','a=1e+8','x=1979-05-27','t=07:32:00','t=1979-05-27T07:32:00Z','a=[1,2,]','[a]\nb=1','[a.b]\nx=1\n[a]\nz=2','a.b=2\na=1','[[rows]]\na=2\n[[rows]]\na=3','x="\\e"','a="\\x61"','x="\\u0000"','a=[1, #comment\n2]','a = 1\na = 2','k. .z=1','x = "a" # comment','a=-nan','a = +inf','a = 1_0_00','x=1__2','hello world','[a]\n[a]','x="\u0001"','x=2020-03-01 13:05:12.003','abc = ["s", 10, false]','\ufeffa=1','x=16:72:01']
    add('tomli','','loads',[([x],{}) for x in tomls])
    pats=['','*','**','**/foo','foo/**','foo/**/*','/foo','foo/bar/','!foo','!','###','[ab]','[!a-z]','foo[','f?o','a\\ b','foo\\ ','.*','/#bar','folder/**/test?.py','a//b','/','foo/**/**/x','[z-a]','*.py[cod]','a[b-d]','a[!0-9]','\\!xyz','#a',' leading','trailing ','hëllo','**/','!!a','\\','a/**b/c','**/*/foo','/a/../b']
    add('pathspec','patterns.gitwildmatch','GitWildMatchPattern.pattern_to_regex',[]) # method calls resolved below through constructor-free classmethod wrapper
    add('pathspec','util','normalize_file',[([x],{}) for x in pats])
    add('pathspec','patterns.gitwildmatch','GitWildMatchPattern',[([s],{}) for s in pats],'pattern')
    numbers=[-123456789,-1,-0.5,0,0.0001,0.5,1,1.9999,2,10,11,12,13,19,21,22,23,99,100,999,1000,1023,1024,1000000,1000000000,10**15,10**21]
    for fn in ['intcomma','intword','ordinal','apnumber','fractional','naturalsize','scientific']:
        add('humanize','',fn,[([n],{}) for n in numbers])
    add('humanize','','naturalsize',[([n],kw) for n in numbers for kw in [{'binary':True},{'gnu':True}]])
    for r in rows:r['key']=sha(canon(r).encode())[:18]
    assert len(rows)==len({r['key'] for r in rows});return rows
if __name__=='__main__':save(ROOT/'roster.json',cases());print(len(cases()))

