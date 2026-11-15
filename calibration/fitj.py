import math
T={"white":(255,255,255),"bf":(191,191,191),"g80":(128,128,128),"g40":(64,64,64),"red":(255,0,0),"lime":(0,255,0),"blue":(0,0,255),"yellow":(255,255,0),"cyan":(0,255,255),"magenta":(255,0,255),"salmon":(250,128,114),"orange":(255,128,0),"violet":(128,0,255),"purple":(128,0,128),"brown":(128,64,0),"peach":(255,192,160)}
SDR={"white":(986,994,838),"bf":(715,721,608),"g80":(469,473,399),"g40":(224,226,190),"red":(827,255,112),"lime":(508,942,251),"blue":(105,179,803),"yellow":(972,971,272),"cyan":(531,961,827),"magenta":(841,313,792),"salmon":(848,506,367),"orange":(862,499,169),"violet":(406,218,801),"purple":(393,148,369)}
HDR={"white":(690,695,586),"bf":(614,619,522),"g80":(462,465,392),"g40":(187,189,159),"red":(571,171,63),"lime":(308,579,144),"blue":(47,111,520),"yellow":(576,586,154),"cyan":(312,582,490),"magenta":(527,189,491),"salmon":(528,317,216),"orange":(536,313,89),"violet":(257,143,500),"purple":(304,121,285),"brown":(335,203,61),"peach":(630,513,351)}
def solve(A,b):
    n=len(b); M=[A[i][:]+[b[i]] for i in range(n)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(M[r][c])); M[c],M[p]=M[p],M[c]
        for r in range(n):
            if r!=c:
                f=M[r][c]/M[c][c]; M[r]=[M[r][j]-f*M[c][j] for j in range(n+1)]
    return [M[i][n]/M[i][i] for i in range(n)]
def feats(l):
    r,g,b=l; return [r,g,b,math.sqrt(r*g),math.sqrt(g*b),math.sqrt(r*b)]
W=SDR["white"]  # one normalisation for both
def lin(v,gam): return [max(v[i]/W[i],0)**gam for i in range(3)]
def fit(sets,gam,tgam):
    rows=[]
    for S,wscale in sets:
        for k,v in S.items():
            w=4 if k=="white" else 2 if k in("salmon","peach","orange","brown") else 1
            # target scaled by measured white level ratio so HDR targets are dimmer, keeps homogeneity
            tg=[(t/255)**tgam*wscale for t in T[k]]
            rows.append((feats(lin(v,gam)),tg,w))
    Mt=[]
    for ch in range(3):
        ATA=[[sum(w*a[i]*a[j] for a,b,w in rows)+(1e-5 if i==j else 0) for j in range(6)] for i in range(6)]
        ATb=[sum(w*a[i]*b[ch] for a,b,w in rows) for i in range(6)]
        Mt.append(solve(ATA,ATb))
    return Mt
def apply(Mt,v,gam,tgam):
    f=feats(lin(v,gam)); return [round(255*min(max(sum(Mt[c][j]*f[j] for j in range(6)),0),1)**(1/tgam)) for c in range(3)]
for gam,tgam in ((1.0,1.0),(1.0,2.2),(2.2,2.2)):
    hs=(sum(HDR["white"])/sum(SDR["white"]))**gam
    Mt=fit([(SDR,1.0),(HDR,hs)],gam,tgam)
    err=0;n=0;lines=[]
    for name,S,sc in (("SDR",SDR,1.0),("HDR",HDR,hs)):
        for k,v in S.items():
            o=apply(Mt,v,gam,tgam); want=[round(255*((t/255)**tgam*sc)**(1/tgam)) for t in T[k]]
            err+=sum((o[i]-want[i])**2 for i in range(3)); n+=3
            if k in("white","red","salmon","orange","peach","purple","g40"): lines.append(f"   {name} {k:7} {o} want {want}")
    print(f"gam {gam}/{tgam} rms {(err/n)**.5:.1f}  coeffs {[[round(x,3) for x in r] for r in Mt]}"); print("\n".join(lines))
