"""Stable-packet certificates with exact integers and symbolic recession directions."""
INF=1<<55
LIMIT=1<<30
def radius(d,lo,hi):
    return abs(lo if d<0 else hi)
def hull(x,y,a,b):
    if abs(x)>a or abs(y)>b:return False
    if x==0 or y==0 or a==INF or b==INF:return True
    return abs(x)*b+abs(y)*a<=a*b
def policies(x,y,ix,iy):
    a=radius(x,*ix);b=radius(y,*iy)
    return (abs(x)<=a and abs(y)<=b,
            hull(x,y,min(a,LIMIT),min(b,LIMIT)),
            hull(x,y,a,b),
            (not x or a==INF) and (not y or b==INF))
def probes(bounds_a,bounds_b):
    from itertools import product
    main=list(product((-LIMIT,-(1<<28),-(1<<26),1<<26,1<<28,LIMIT),repeat=2))
    ax=[max(-LIMIT,bounds_a[0]),min(LIMIT,bounds_a[1])]
    ay=[max(-LIMIT,bounds_b[0]),min(LIMIT,bounds_b[1])]
    diag=set(product(ax,ay))
    half=lambda x:(1 if x>=0 else -1)*(abs(x)//2)
    diag.update((half(x),half(y)) for x,y in product(ax,ay))
    return main,sorted(diag)
