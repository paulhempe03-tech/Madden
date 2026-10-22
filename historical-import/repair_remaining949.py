from pathlib import Path
import io
import pandas as pd, requests
import build_remaining949 as b
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'output_remaining949'
TARGETS=pd.read_csv(ROOT/'targets_remaining949.csv')
OVR=pd.read_csv(ROOT/'mapping_overrides_remaining949.csv')
MAP=pd.read_csv(OUT/'remaining949_player_mapping.csv')
BULK=pd.read_csv(OUT/'remaining949_historical_stats_bulk.csv',low_memory=False)
PLAYERS=pd.read_csv(io.BytesIO(requests.get(b.PLAYERS_URL,timeout=90).content),low_memory=False)

def force(pid,gsis):
 m=MAP.internal_player_id.eq(int(pid))
 if m.sum()!=1: raise SystemExit(f'override pid {pid} match count={m.sum()}')
 MAP.loc[m,'gsis_id']=str(gsis); MAP.loc[m,'mapping_status']='OVERRIDE_VERIFIED'; MAP.loc[m,'note']='verified current-player identity override'
for _,r in OVR.iterrows(): force(r.internal_player_id,r.gsis_id)

over_ids=set(OVR.internal_player_id.astype(int))
over_names=set(TARGETS[TARGETS.player_id.isin(over_ids)].player_name.astype(str))
BULK=BULK[~BULK.player_name.astype(str).isin(over_names)].copy()
by={}
for _,m in MAP[MAP.internal_player_id.isin(over_ids)].iterrows():
 by[str(m.gsis_id)]={'internal_player_id':int(m.internal_player_id),'player_name':m.player_name,'position':m.position}
gs=set(by)
wp=[]; rp=[]; dl=[]
for y in b.YEARS:
 try:
  s=b.get_csv(b.STATS_URL.format(year=y)); sid=b.pick_col(s,'player_id','gsis_id'); sf=s[s[sid].astype(str).isin(gs)].copy() if sid else pd.DataFrame()
  if not sf.empty: sf['_year']=y; sf['_gsis']=sf[sid].astype(str); wp.append(sf)
  dl.append((y,'stats','OK'))
 except Exception as e: dl.append((y,'stats','ERROR:'+str(e)))
 try:
  r=b.get_csv(b.ROSTER_URL.format(year=y)); rid=b.pick_col(r,'gsis_id','player_id'); rf=r[r[rid].astype(str).isin(gs)].copy() if rid else pd.DataFrame()
  if not rf.empty: rf['_year']=y; rf['_gsis']=rf[rid].astype(str); rp.append(rf)
  dl.append((y,'roster','OK'))
 except Exception as e: dl.append((y,'roster','ERROR:'+str(e)))
if any(x[2]!='OK' for x in dl): raise SystemExit([x for x in dl if x[2]!='OK'])
stats=pd.concat(wp,ignore_index=True) if wp else pd.DataFrame(); rosters=pd.concat(rp,ignore_index=True) if rp else pd.DataFrame()
records={}
if not rosters.empty:
 tc=b.pick_col(rosters,'team','team_abbr','recent_team')
 for (g,y,team),_ in rosters.groupby(['_gsis','_year',tc],dropna=False):
  if g not in by: continue
  t=by[g]; team='' if pd.isna(team) else str(team); key=(t['internal_player_id'],int(y),team)
  rec={c:0 for c in b.MASTER_COLS}; rec.update({'year':int(y),'player_name':t['player_name'],'position':t['position'],'team':team,'source':'nflverse weekly stats + season roster; verified remaining949 override'}); records[key]=rec
if not stats.empty:
 tc=b.pick_col(stats,'recent_team','team','team_abbr'); sc=b.pick_col(stats,'season_type')
 if not sc: stats['_stype']='REG'; sc='_stype'
 for (g,y,st,team),grp in stats.groupby(['_gsis','_year',sc,tc],dropna=False):
  if g not in by: continue
  t=by[g]; team='' if pd.isna(team) else str(team); key=(t['internal_player_id'],int(y),team)
  if key not in records:
   rec={c:0 for c in b.MASTER_COLS}; rec.update({'year':int(y),'player_name':t['player_name'],'position':t['position'],'team':team,'source':'nflverse weekly player stats; verified remaining949 override'}); records[key]=rec
  records[key].update(b.agg(grp,'post_' if str(st).upper().startswith('POST') else ''))
repair=pd.DataFrame(list(records.values()))
for c in b.MASTER_COLS:
 if c not in repair.columns: repair[c]=0
if not repair.empty: repair=repair[b.MASTER_COLS]
final=pd.concat([BULK,repair],ignore_index=True)[b.MASTER_COLS].sort_values(['player_name','year','team']).reset_index(drop=True)
final.to_csv(OUT/'remaining949_historical_stats_final.csv',index=False)
MAP.to_csv(OUT/'remaining949_player_mapping_final.csv',index=False)

meta=PLAYERS.drop_duplicates('gsis_id').set_index('gsis_id')
aud=[]
for i,t in TARGETS.reset_index(drop=True).iterrows():
 m=MAP[MAP.internal_player_id.eq(int(t.player_id))].iloc[0]
 n=int((final.player_name.astype(str)==str(t.player_name)).sum())
 rookie=''; last=''; team=''
 if str(m.gsis_id) in meta.index:
  p=meta.loc[str(m.gsis_id)]
  if isinstance(p,pd.DataFrame): p=p.iloc[0]
  rookie=p.get('rookie_season',''); last=p.get('last_season',''); team=p.get('latest_team','')
 if n>0: status='FINAL_READY'
 elif pd.notna(rookie) and str(rookie)!='' and int(float(rookie))==2026: status='NO_PRE2026_HISTORY'
 else: status='SOURCE_GAP'
 aud.append([i+1001,int(t.player_id),t.player_name,t.position,m.gsis_id,m.mapping_status,n,rookie,last,team,status])
AUD=pd.DataFrame(aud,columns=['rank','internal_player_id','player_name','position','gsis_id','mapping_status','historical_rows','rookie_season','last_season','latest_team','status'])
AUD.to_csv(OUT/'remaining949_audit_final.csv',index=False)
bdir=OUT/'blocks_final'; bdir.mkdir(exist_ok=True)
for i in range(95): AUD.iloc[i*10:min((i+1)*10,949)].to_csv(bdir/f'block_{i+101:03d}_audit.csv',index=False)
keys=final[['player_name','year','team']].astype(str).agg('|'.join,axis=1)
summary={'targets':len(AUD),'unique_ids':AUD.internal_player_id.nunique(),'unique_names':AUD.player_name.nunique(),'historical_rows':len(final),'final_ready':int((AUD.status=='FINAL_READY').sum()),'no_pre2026_history':int((AUD.status=='NO_PRE2026_HISTORY').sum()),'source_gap':int((AUD.status=='SOURCE_GAP').sum()),'unresolved_mapping':int(AUD.mapping_status.isin(['MISSING','REVIEW']).sum()),'duplicate_player_year_team_rows':int(keys.duplicated().sum()),'blocks':95}
(OUT/'remaining949_final_summary.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n')
print(summary)
if summary['source_gap']: print(AUD[AUD.status=='SOURCE_GAP'].to_string(index=False))
assert summary['targets']==949 and summary['unique_ids']==949 and summary['unique_names']==949
assert summary['unresolved_mapping']==0
assert summary['source_gap']==0
assert summary['duplicate_player_year_team_rows']==0
assert summary['final_ready']+summary['no_pre2026_history']==949
