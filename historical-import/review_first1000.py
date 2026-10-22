import io, re, unicodedata
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
PLAYERS_URL='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',s)
    return re.sub(r'[^a-z0-9]','',s)

players=pd.read_csv(io.BytesIO(requests.get(PLAYERS_URL,timeout=90).content),low_memory=False)
mapping=pd.read_csv(OUT/'first1000_player_mapping.csv')
audit=pd.read_csv(OUT/'first1000_audit.csv')
name_col=next(c for c in ['display_name','full_name','football_name','name','short_name'] if c in players.columns)
gsis_col=next(c for c in ['gsis_id','player_id'] if c in players.columns)
pos_col=next((c for c in ['position','position_group'] if c in players.columns),None)
players['_norm']=players[name_col].map(norm)

un=mapping[mapping.mapping_status.isin(['MISSING','REVIEW'])]
rows=[]
for _,u in un.iterrows():
    q=norm(u.player_name)
    # Score all names; position is surfaced for human-safe resolution rather than auto-forced.
    cand=[]
    for _,p in players.iterrows():
        pn=p['_norm']
        if not pn: continue
        sc=SequenceMatcher(None,q,pn).ratio()
        cand.append((sc,p))
    cand=sorted(cand,key=lambda x:x[0],reverse=True)[:5]
    for rank,(sc,p) in enumerate(cand,1):
        rows.append({
            'internal_player_id':u.internal_player_id,'player_name':u.player_name,'app_position':u.position,
            'mapping_status':u.mapping_status,'candidate_rank':rank,'similarity':round(sc,4),
            'candidate_name':p.get(name_col,''),'candidate_position':p.get(pos_col,'') if pos_col else '',
            'candidate_gsis_id':p.get(gsis_col,'')
        })
pd.DataFrame(rows).to_csv(OUT/'unresolved_mapping_candidates.csv',index=False)

# Inspect mapped players with no historical rows and surface nflverse career metadata.
nohist=audit[audit.status=='NO_PRE2026_HISTORY_OR_SOURCE_GAP'].copy()
pmeta=players.drop_duplicates(gsis_col).copy()
meta_cols=[c for c in ['rookie_season','rookie_year','entry_year','years_of_experience','last_season','latest_team','status','birth_date'] if c in pmeta.columns]
lookup=pmeta.set_index(gsis_col)
rev=[]
for _,r in nohist.iterrows():
    rec=r.to_dict(); gs=str(r.gsis_id)
    if gs in lookup.index:
        p=lookup.loc[gs]
        if isinstance(p,pd.DataFrame): p=p.iloc[0]
        for c in meta_cols: rec[c]=p.get(c,'')
    rev.append(rec)
pd.DataFrame(rev).to_csv(OUT/'no_history_review.csv',index=False)
(OUT/'players_schema.txt').write_text('\n'.join(players.columns.astype(str))+'\n')
print(f'unresolved={len(un)} no_history_review={len(nohist)} meta_cols={meta_cols}')
