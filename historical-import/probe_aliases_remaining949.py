import io,pandas as pd,requests
u='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
p=pd.read_csv(io.BytesIO(requests.get(u,timeout=90).content),low_memory=False)
cols=[c for c in ['gsis_id','display_name','football_name','first_name','last_name','position','position_group','rookie_season','last_season','latest_team','status','espn_id','pfr_id'] if c in p.columns]
mask=pd.Series(False,index=p.index)
for c in ['display_name','football_name','first_name','last_name']:
 if c in p.columns:
  mask |= p[c].astype(str).str.contains('Slaton|Okoye|Reid|Ogletree|Mauigoa',case=False,regex=True,na=False)
p.loc[mask,cols].to_csv('historical-import/alias_probe_remaining949.csv',index=False)
print(p.loc[mask,cols].to_string(index=False))
