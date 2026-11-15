W=[445,462,461.]
P={ # name: (measured10, target rgb 0-255)
"white":([445,462,461],(255,255,255)),"grey50":([212,220,220],(128,128,128)),"grey25":([101,105,104],(64,64,64)),
"red":([406,128,54],(255,0,0)),"lime":([215,446,112],(0,255,0)),"blue":([57,86,500],(0,0,255)),
"yellow":([428,448,119],(255,255,0)),"cyan":([230,454,450],(0,255,255)),"magenta":([411,156,466],(255,0,255)),
"salmon":([404,224,178],(250,128,114)),"orange":([417,224,70],(255,128,0)),"violet":([196,120,491],(128,0,255)),
"purple":([185,64,214],(128,0,128)),"brown":([192,106,33],(128,64,0)),"peach":([424,337,262],(255,192,160)),"black":([0,0,0],(0,0,0))}
wt={k:1 for k in P}; wt["white"]=6; wt["grey50"]=3; wt["grey25"]=2; wt["salmon"]=3
def solve(A,b):
    n=len(b); M=[A[i][:]+[b[i]] for i in range(n)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(M[r][c])); M[c],M[p]=M[p],M[c]
        for r in range(n):
            if r!=c:
                f=M[r][c]/M[c][c]; M[r]=[M[r][j]-f*M[c][j] for j in range(n+1)]
    return [M[i][n]/M[i][i] for i in range(n)]
def fit(gam):
    lin=lambda v:[max(v[i]/W[i],0)**gam for i in range(3)]
    rows=[(lin(m),[(t/255)**gam for t in tg],wt[k]) for k,(m,tg) in P.items()]
    Mt=[]
    for ch in range(3):
        ATA=[[sum(w*a[i]*a[j] for a,b,w in rows) for j in range(3)] for i in range(3)]
        ATb=[sum(w*a[i]*b[ch] for a,b,w in rows) for i in range(3)]
        Mt.append(solve(ATA,ATb))
    err=0;out={}
    for k,(m,tg) in P.items():
        l=lin(m); o=[round(255*min(max(sum(Mt[c][j]*l[j] for j in range(3)),0),1)**(1/gam)) for c in range(3)]
        out[k]=o; err+=sum((o[i]-tg[i])**2 for i in range(3))
    return Mt,out,err
for gam in (1.0,1.5,2.2):
    Mt,out,err=fit(gam)
    print(f"gamma {gam} rms={(err/len(P)/3)**.5:.1f} M={[[round(x,3) for x in r] for r in Mt]}")
    for k in ["white","grey50","salmon","peach","orange","violet","purple","yellow","cyan","red","lime","blue"]:
        print(f"   {k:7} {out[k]} want {list(P[k][1])}")
print("==== root-polynomial")
import math
def feats(l):
    r,g,b=l
    return [r,g,b,math.sqrt(r*g),math.sqrt(g*b),math.sqrt(r*b)]
def fitrp(gam,ridge=1e-4):
    lin=lambda v:[max(v[i]/W[i],0)**gam for i in range(3)]
    rows=[(feats(lin(m)),[(t/255)**gam for t in tg],wt[k]) for k,(m,tg) in P.items()]
    n=6;Mt=[]
    for ch in range(3):
        ATA=[[sum(w*a[i]*a[j] for a,b,w in rows)+(ridge if i==j else 0) for j in range(n)] for i in range(n)]
        ATb=[sum(w*a[i]*b[ch] for a,b,w in rows) for i in range(n)]
        Mt.append(solve(ATA,ATb))
    err=0;out={}
    for k,(m,tg) in P.items():
        f=feats(lin(m)); o=[round(255*min(max(sum(Mt[c][j]*f[j] for j in range(n)),0),1)**(1/gam)) for c in range(3)]
        out[k]=o; err+=sum((o[i]-tg[i])**2 for i in range(3))
    return Mt,out,err
for gam in (1.0,2.2):
    Mt,out,err=fitrp(gam)
    print(f"gamma {gam} rms={(err/len(P)/3)**.5:.1f}")
    print("  M=",[[round(x,3) for x in r] for r in Mt])
    for k in P: print(f"   {k:8} {out[k]} want {list(P[k][1])}")
