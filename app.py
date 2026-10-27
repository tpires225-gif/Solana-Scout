from flask import Flask, jsonify, render_template
import urllib.request, json, datetime, re
app=Flask(__name__)
BASE="https://api.dexscreener.com"
def fetch(path):
    req=urllib.request.Request(BASE+path,headers={"User-Agent":"SolanaScoutWeb/1.0"})
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)
@app.get("/")
def home(): return render_template("index.html")
@app.get("/api/token/<address>")
def lookup(address):
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", address):
        return jsonify(error="Invalid Solana contract"), 400
    try:
        pairs=fetch("/tokens/v1/solana/"+address)
        matches=[p for p in pairs if p.get("chainId")=="solana" and p.get("baseToken",{}).get("address")==address]
        if not matches: return jsonify(error="Token not found"), 404
        return jsonify(pair=max(matches,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0)))
    except Exception:
        return jsonify(error="Lookup temporarily unavailable"), 503

@app.get("/api/scan")
def scan():
    addresses=[]
    errors=0
    for endpoint in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"):
        try:
            addresses.extend(x["tokenAddress"] for x in fetch(endpoint) if x.get("chainId")=="solana" and x.get("tokenAddress"))
        except Exception: errors+=1
    addresses=list(dict.fromkeys(addresses))[:90]
    pairs=[]
    for i in range(0,len(addresses),30):
        try: pairs+=fetch("/tokens/v1/solana/"+",".join(addresses[i:i+30]))
        except Exception: errors+=1
    best={}
    for p in pairs:
        if p.get("chainId")!="solana": continue
        a=p.get("baseToken",{}).get("address")
        if a not in addresses: continue
        if a not in best or float(p.get("liquidity",{}).get("usd") or 0)>float(best[a].get("liquidity",{}).get("usd") or 0): best[a]=p
    rows=[]
    for a,p in best.items():
        liq=float(p.get("liquidity",{}).get("usd") or 0)
        cap=float(p.get("marketCap") or p.get("fdv") or 0)
        vol=float(p.get("volume",{}).get("h1") or 0)
        tx=p.get("txns",{}).get("h1",{})
        buys=int(tx.get("buys") or 0); sells=int(tx.get("sells") or 0)
        change=float(p.get("priceChange",{}).get("h1") or 0)
        created=p.get("pairCreatedAt")
        age=(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000-created)/60000 if created else None
        score=(20 if liq>=50000 else 10 if liq>=10000 else 0)+(20 if vol>=100000 else 10 if vol>=20000 else 0)+(15 if buys>=100 and buys>sells else 7 if buys>sells else 0)+(15 if 5<=change<=80 else 6 if 0<change<150 else 0)+(15 if age is not None and 15<=age<=1440 else 5 if age is not None and age<=4320 else 0)
        rows.append(dict(name=p.get("baseToken",{}).get("name",""),buy_sell_ratio=round(buys/max(sells,1),2),symbol=p.get("baseToken",{}).get("symbol","?"),address=a,liquidity=liq,cap=cap,volume=vol,buys=buys,sells=sells,change=change,age=round(age) if age is not None else None,score=score,status="THIN LIQUIDITY" if liq<10000 else "WATCH" if score>=65 else "MONITOR" if score>=40 else "LOW DATA",url=p.get("url","")))
    if not rows and errors: return jsonify(error="Unable to retrieve fresh DexScreener data"),503
    return jsonify(rows=sorted(rows,key=lambda x:x["score"],reverse=True),
                   updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   partial=bool(errors))
if __name__=="__main__": app.run(host="0.0.0.0",port=10000)
