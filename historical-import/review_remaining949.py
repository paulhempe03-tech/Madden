from pathlib import Path
from difflib import SequenceMatcher
import io, re, unicodedata
import pandas as pd, requests
import build_remaining949 as b
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'output_remaining949'
players=pd.read_csv(io.BytesIO(requests.get(b.PLAYERS_URL,timeout=90).content),low_memory=False)
mapdf=pd.read_csv(OUT/'remaining949_player_mapping.csv'); audit=pd.read_csv(OUT/'remaining949_audit.csv')
def norm(v):
 s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',s); return re.sub(r'[^a-z0-9]','',s)
name_col=next(c for c in ['display_name','full_name','football_name','name','short_name'] if c in players.columns)
gsis_col=next(c for c in ['gsis_id','player_id'] if c in players.columns)
pos_col=next((c for c in ['position','position_group'] if c in players.columns),None)
players['_norm']=players[name_col].map(norm)
rows=[]
for _,u in mapdf[mapdf.mapping_status.isin(['MISSING','REVIEW'])].iterrows():
 q=norm(u.player_name); pool=players[players._norm.str[:1].eq(q[:1])] if q else players
 cand=[]
 for _,p in pool.iterrows():
  pn=p['_norm'];
  if not pn: continue
  sc=SequenceMatcher(None,q,pn).ratio(); cand.append((sc,p))
 for rank,(sc,p) in enumerate(sorted(cand,key=lambda x:x[0],reverse=True)[:5],1):
  rows.append({'internal_player_id':u.internal_player_id,'player_name':u.player_name,'app_position':u.position,'mapping_status':u.mapping_status,
  'candidate_rank':rank,'similarity':round(sc,4),'candidate_name':p.get(name_col,''),'candidate_position':p.get(pos_col,'') if pos_col else '',
  'candidate_gsis_id':p.get(gsis_col,''),'rookie_season':p.get('rookie_season',''),'last_season':p.get('last_season',''),'latest_team':p.get('latest_team',''),'status':p.get('status','')})
pd.DataFrame(rows).to_csv(OUT/'unresolved_mapping_candidates.csv',index=False)
lookup=players.drop_duplicates(gsis_col).set_index(gsis_col)
rev=[]
for _,r in audit[audit.status=='NO_PRE2026_HISTORY_OR_SOURCE_GAP'].iterrows():
 rec=r.to_dict(); gs=str(r.gsis_id)
 if gs in lookup.index:
  p=lookup.loc[gs];
  if isinstance(p,pd.DataFrame): p=p.iloc[0]
  for c in ['rookie_season','years_of_experience','last_season','latest_team','status','birth_date']:
   rec[c]=p.get(c,'')
 rev.append(rec)
pd.DataFrame(rev).to_csv(OUT/'no_history_review.csv',index=False)
print('unresolved',len(mapdf[mapdf.mapping_status.isin(['MISSING','REVIEW'])]),'no_history',len(rev))
