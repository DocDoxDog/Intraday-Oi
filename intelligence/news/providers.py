from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import requests

GDELT_DOC_URL="https://api.gdeltproject.org/api/v2/doc/doc"
FOREX_FACTORY_JSON_URL="https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def _get(url:str, *, params:dict[str,Any]|None=None, timeout:int=20):
    r=requests.get(url,params=params,timeout=timeout,headers={"User-Agent":"Intraday-Oi-News/1.0"}); r.raise_for_status(); return r

def fetch_gdelt(query:str='(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike OR military OR invasion OR attack)', *, timespan:str='24h', maxrecords:int=25)->list[dict[str,Any]]:
    payload=_get(GDELT_DOC_URL,params={"query":query,"mode":"artlist","maxrecords":max(1,min(int(maxrecords),250)),"timespan":timespan,"sort":"datedesc","format":"json"}).json()
    out=[]
    for a in (payload.get("articles",[]) if isinstance(payload,dict) else []):
        title=str(a.get("title") or "").strip(); url=str(a.get("url") or "").strip(); seen=str(a.get("seendate") or "").strip()
        if not title or not url or not seen: continue
        try: ts=datetime.strptime(seen,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError: continue
        out.append({"headline":title,"source":str(a.get("domain") or "GDELT"),"url":url,"published_at":ts,"language":str(a.get("language") or "en"),"category":"GEOPOLITICAL","assets":("GOLD","USD","USOIL","UKOIL"),"severity":"MEDIUM"})
    return out

def fetch_forex_factory_calendar(*,url:str=FOREX_FACTORY_JSON_URL)->list[dict[str,Any]]:
    payload=_get(url).json()
    if not isinstance(payload,list): raise ValueError("FOREX_FACTORY_INVALID_PAYLOAD")
    severity={"High":"HIGH","Medium":"MEDIUM","Low":"LOW","Holiday":"IGNORE"}
    out=[]
    for e in payload:
        if not isinstance(e,dict): continue
        title=str(e.get("title") or "").strip(); country=str(e.get("country") or "").strip().upper(); raw=str(e.get("date") or "").strip()
        if not title or not country or not raw: continue
        try: dt=datetime.fromisoformat(raw.replace("Z","+00:00")); dt=dt.astimezone(timezone.utc) if dt.tzinfo else None
        except ValueError: dt=None
        if dt is None: continue
        impact=str(e.get("impact") or "Low").strip()
        out.append({"headline":f"{country} — {title}","source":"Forex Factory","url":"https://www.forexfactory.com/calendar/","published_at":dt,"event_time":dt,"language":"en","category":"MACRO","entities":(country,),"assets":("GOLD","USD") if country=="USD" else ("GOLD",),"severity":severity.get(impact,"LOW"),"calendar":{"country":country,"impact":impact,"forecast":str(e.get("forecast") or ""),"previous":str(e.get("previous") or "")}})
    return out

def fetch_free_news_bundle(*,gdelt_query:str='(war OR conflict OR missile OR sanctions OR ceasefire OR airstrike OR military OR invasion OR attack)',gdelt_timespan:str='24h',gdelt_maxrecords:int=25)->list[dict[str,Any]]:
    out=[]
    try: out.extend(fetch_gdelt(gdelt_query,timespan=gdelt_timespan,maxrecords=gdelt_maxrecords))
    except requests.RequestException as exc: print(f"⚠️  GDELT feed unavailable: {exc}")
    try: out.extend(fetch_forex_factory_calendar())
    except requests.RequestException as exc: print(f"⚠️  Forex Factory feed unavailable: {exc}")
    return out
