from pathlib import Path
import pandas as pd
import requests, io

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
players=pd.read_csv(io.BytesIO(requests.get('https://github.com/nflverse/nflverse-data/releases/download/players/players.csv',timeout=90).content),low_memory=False)
cand=pd.read_csv(OUT/'unresolved_mapping_candidates.csv')
ids=set(cand['candidate_gsis_id'].dropna().astype(str))
# include David Bailey correct-current search candidates by name too
subset=players[players['gsis_id'].astype(str).isin(ids)].copy()
cols=[c for c in ['gsis_id','display_name','football_name','position','position_group','rookie_season','last_season','latest_team','status','years_of_experience','draft_year','draft_round','draft_pick','draft_team','pfr_id','espn_id'] if c in subset.columns]
meta=subset[cols].drop_duplicates('gsis_id')
merged=cand.merge(meta,left_on='candidate_gsis_id',right_on='gsis_id',how='left',suffixes=('','_meta'))
merged.to_csv(OUT/'unresolved_mapping_candidates_with_meta.csv',index=False)
# David Bailey candidates from current players table
db=players[players['display_name'].astype(str).str.contains('David Bailey',case=False,na=False)].copy()
db[cols].to_csv(OUT/'david_bailey_candidates.csv',index=False)
print(f'unresolved_rows={len(merged)} david_bailey_candidates={len(db)}')
