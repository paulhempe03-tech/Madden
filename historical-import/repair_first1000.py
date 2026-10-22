from pathlib import Path
import pandas as pd
import requests, io
import build_first1000 as b

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
TARGETS=pd.read_csv(ROOT/'targets_first1000.csv')
OVR=pd.read_csv(ROOT/'mapping_overrides.csv')
MAP=pd.read_csv(OUT/'first1000_player_mapping.csv')
BULK=pd.read_csv(OUT/'first1000_historical_stats_bulk.csv',low_memory=False)
PLAYERS=pd.read_csv(io.BytesIO(requests.get(b.PLAYERS_URL,timeout=90).content),low_memory=False)

def force_mapping(pid, gsis, status='OVERRIDE_VERIFIED'):
    mask=MAP.internal_player_id.eq(pid)
    MAP.loc[mask,'gsis_id']=gsis
    MAP.loc[mask,'mapping_status']=status
    MAP.loc[mask,'note']='verified current-player identity override'

# Reviewed ambiguous players.
for _,r in OVR.iterrows():
    force_mapping(int(r.internal_player_id),str(r.gsis_id))

# Fix David Bailey: select the 2026 rookie only, never the historical namesake.
db=PLAYERS[(PLAYERS.display_name.astype(str).str.lower()=='david bailey') & (pd.to_numeric(PLAYERS.rookie_season,errors='coerce')==2026)]
if len(db)!=1:
    raise SystemExit(f'Expected one 2026 David Bailey, found {len(db)}')
david_gsis=str(db.iloc[0].gsis_id)
force_mapping(1887,david_gsis,'OVERRIDE_2026_ROOKIE')

# Rebuild only the reviewed overrides from source data, preserving all previously auto-built rows.
override_ids=set(OVR.internal_player_id.astype(int))|{1887}
override_names=set(TARGETS[TARGETS.player_id.isin(override_ids)].player_name.astype(str))
BULK=BULK[~BULK.player_name.astype(str).isin(override_names)].copy()

target_by_gsis={}
for _,m in MAP[MAP.internal_player_id.isin(override_ids)].iterrows():
    target_by_gsis[str(m.gsis_id)]={'internal_player_id':int(m.internal_player_id),'player_name':m.player_name,'position':m.position}
mapped_gsis=set(target_by_gsis)

weekly_parts=[]; roster_parts=[]; dl=[]
for year in b.YEARS:
    try:
        s=b.get_csv(b.STATS_URL.format(year=year)); sid=b.pick_col(s,'player_id','gsis_id')
        if sid:
            sf=s[s[sid].astype(str).isin(mapped_gsis)].copy()
            if not sf.empty:
                sf['_year']=year; sf['_gsis']=sf[sid].astype(str); weekly_parts.append(sf)
        dl.append([year,'stats','OK'])
    except Exception as e:
        dl.append([year,'stats',f'ERROR:{e}'])
    try:
        r=b.get_csv(b.ROSTER_URL.format(year=year)); rid=b.pick_col(r,'gsis_id','player_id')
        if rid:
            rf=r[r[rid].astype(str).isin(mapped_gsis)].copy()
            if not rf.empty:
                rf['_year']=year; rf['_gsis']=rf[rid].astype(str); roster_parts.append(rf)
        dl.append([year,'roster','OK'])
    except Exception as e:
        dl.append([year,'roster',f'ERROR:{e}'])

if any(not x[2].startswith('OK') for x in dl):
    raise SystemExit('Override source download failure: '+repr([x for x in dl if not x[2].startswith('OK')]))

stats=pd.concat(weekly_parts,ignore_index=True) if weekly_parts else pd.DataFrame()
rosters=pd.concat(roster_parts,ignore_index=True) if roster_parts else pd.DataFrame()
records={}
if not rosters.empty:
    teamc=b.pick_col(rosters,'team','team_abbr','recent_team')
    if teamc:
        for (gsis,year,team),g in rosters.groupby(['_gsis','_year',teamc],dropna=False):
            if gsis not in target_by_gsis: continue
            t=target_by_gsis[gsis]; team='' if pd.isna(team) else str(team)
            rec={c:0 for c in b.MASTER_COLS}
            rec.update({'year':int(year),'player_name':t['player_name'],'position':t['position'],'team':team,
                        'source':'nflverse weekly stats + season roster; verified override'})
            records[(t['internal_player_id'],int(year),team)]=rec
if not stats.empty:
    teamc=b.pick_col(stats,'recent_team','team','team_abbr'); stypec=b.pick_col(stats,'season_type')
    if not teamc: raise SystemExit('weekly stats have no team column')
    if not stypec: stats['_stype']='REG'; stypec='_stype'
    for (gsis,year,stype,team),g in stats.groupby(['_gsis','_year',stypec,teamc],dropna=False):
        if gsis not in target_by_gsis: continue
        t=target_by_gsis[gsis]; team='' if pd.isna(team) else str(team)
        key=(t['internal_player_id'],int(year),team)
        if key not in records:
            rec={c:0 for c in b.MASTER_COLS}
            rec.update({'year':int(year),'player_name':t['player_name'],'position':t['position'],'team':team,
                        'source':'nflverse weekly player stats; verified override'})
            records[key]=rec
        records[key].update(b.aggregate_group(g,'post_' if str(stype).upper().startswith('POST') else ''))

repair=pd.DataFrame(list(records.values()))
for c in b.MASTER_COLS:
    if c not in repair.columns: repair[c]=0
if not repair.empty: repair=repair[b.MASTER_COLS]
final=pd.concat([BULK,repair],ignore_index=True)
final=final[b.MASTER_COLS].sort_values(['player_name','year','team']).reset_index(drop=True)
final.to_csv(OUT/'first1000_historical_stats_final.csv',index=False)
MAP.to_csv(OUT/'first1000_player_mapping_final.csv',index=False)

# Classify every target. 2026 rookies legitimately have no pre-2026 NFL row.
meta=PLAYERS.drop_duplicates('gsis_id').set_index('gsis_id')
aud=[]
for rank,t in TARGETS.reset_index(drop=True).iterrows():
    m=MAP[MAP.internal_player_id.eq(int(t.player_id))].iloc[0]
    n=int((final.player_name.astype(str)==str(t.player_name)).sum())
    rookie=''
    if str(m.gsis_id) in meta.index:
        p=meta.loc[str(m.gsis_id)]
        if isinstance(p,pd.DataFrame): p=p.iloc[0]
        rookie=p.get('rookie_season','')
    if rank<10:
        status='KEEP_EXISTING_MANUAL_BLOCK001'
    elif n>0:
        status='FINAL_READY'
    elif pd.notna(rookie) and int(float(rookie))==2026:
        status='NO_PRE2026_HISTORY'
    else:
        status='SOURCE_GAP'
    aud.append([rank+1,int(t.player_id),t.player_name,t.position,m.gsis_id,m.mapping_status,n,rookie,status])
AUD=pd.DataFrame(aud,columns=['rank','internal_player_id','player_name','position','gsis_id','mapping_status','historical_rows','rookie_season','status'])
AUD.to_csv(OUT/'first1000_audit_final.csv',index=False)
blocks=OUT/'blocks_final'; blocks.mkdir(exist_ok=True)
for i in range(100): AUD.iloc[i*10:(i+1)*10].to_csv(blocks/f'block_{i+1:03d}_audit.csv',index=False)

summary={
 'targets':len(AUD),
 'unique_ids':AUD.internal_player_id.nunique(),
 'unique_names':AUD.player_name.nunique(),
 'historical_rows':len(final),
 'final_ready':int((AUD.status=='FINAL_READY').sum()),
 'manual_block001_preserved':int((AUD.status=='KEEP_EXISTING_MANUAL_BLOCK001').sum()),
 'no_pre2026_history':int((AUD.status=='NO_PRE2026_HISTORY').sum()),
 'source_gap':int((AUD.status=='SOURCE_GAP').sum()),
 'unresolved_mapping':int(AUD.mapping_status.isin(['MISSING','REVIEW']).sum()),
 'blocks':100,
}
(OUT/'first1000_final_summary.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n')
print(summary)
assert summary['targets']==1000 and summary['unique_ids']==1000 and summary['unique_names']==1000
assert summary['unresolved_mapping']==0
assert summary['source_gap']==0
assert summary['final_ready']+summary['manual_block001_preserved']+summary['no_pre2026_history']==1000
