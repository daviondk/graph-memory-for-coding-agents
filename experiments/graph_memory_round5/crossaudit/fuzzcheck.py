"""Additional differential fixture generation, independent of all paper data and predictions."""
import random,string
from independent import evaluate_a,evaluate_b,save,D,sha
rng=random.Random(18_051);frags=['',';', '}', '{', '\n', '#', '//', 'http://', '"','\\', "'",'\r','/*','*/','α', '∫',' true ','_x','25foo','É2','a'*250, 'abc '*60]
def sample():
    return ''.join(rng.choice(frags+[''.join(rng.choices(string.ascii_letters,k=5))]) for _ in range(rng.randrange(24)))
n=5000
for j in range(n):
    p=sample();g=p if j%11==0 else sample()
    a,b=evaluate_a(p,g,str(j)),evaluate_b(p,g)
    assert a==b,(j,p,g,a,b)
save('fuzzcheck.json',dict(generated_pairs=n,disagreements=0,seed=18_051,scorer_sha256=sha(D/'independent.py')))
print(n,'differential fixtures passed.')

