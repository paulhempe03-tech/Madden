from __future__ import annotations
import io, re, unicodedata
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
TARGETS=ROOT/'targets_remaining949.csv'
OUT=ROOT/'output_remaining949'; OUT.mkdir(parents=True,exist_ok=True)
YEARS=range(1999,2026)
PLAYERS_URL='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
STATS_URL='https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv'
ROSTER_URL='https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{year}.csv'
MASTER_COLS=[
'year','player_name','position','team','source','games','pass_att','pass_comp','pass_yards','pass_td','pass_int',
'rush_att','rush_yards','rush_td','targets','receptions','rec_yards','rec_td','sacks','tackles','tfl','forced_fumbles',
'fumble_recoveries','def_interceptions','pressures','pass_breakups','fg_att','fg_made','punts','punt_yards','kick_returns',
'kick_return_yards','kick_return_td','punt_returns','punt_return_yards','punt_return_td','post_games','post_pass_att','post_pass_comp',
'post_pass_yards','post_pass_td','post_pass_int','post_rush_att','post_rush_yards','post_rush_td','post_targets','post_receptions',
'post_rec_yards','post_rec_td','post_sacks','post_tackles','post_tfl','post_forced_fumbles','post_fumble_recoveries',
'post_def_interceptions','post_pressures','post_pass_breakups','post_fg_att','post_fg_made','post_punts','post_punt_yards',
'post_kick_returns','post_kick_return_yards','post_kick_return_td','post_punt_returns','post_punt_return_yards','post_punt_return_td']
APP_POS_TO_NFL={
'HB':{'RB'},'FB':{'FB'},'WR':{'WR'},'TE':{'TE'},'QB':{'QB'},'LT':{'OT','T','LT'},'RT':{'OT','T','RT'},'LG':{'OG','G','LG'},
'RG':{'OG','G','RG'},'C':{'C'},'LEDG':{'DE','EDGE','OLB'},'REDG':{'DE','EDGE','OLB'},'DT':{'DT','NT'},'MIKE':{'LB','ILB','MLB'},
'WILL':{'LB','OLB'},'SAM':{'LB','OLB'},'CB':{'CB'},'FS':{'S','SAF','FS'},'SS':{'S','SAF','SS'},'K':{'K'},'P':{'P'},'LS':{'LS'}}

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\b(jr|sr|ii|iii|iv|v)\b','',s)
    return re.sub(r'[^a-z0-9]','',s)

def get_csv(url,timeout=90):
    r=requests.get(url,timeout=timeout); r.raise_for_status(); return pd.read_csv(io.BytesIO(r.content),low_memory=False)

def pick_col(df,*cs):
    return next((c for c in cs if c in df.columns),None)

def num(df,*cs):
    c=pick_col(df,*cs)
    return pd.to_numeric(df[c],errors='coerce').fillna(0) if c else pd.Series(0.0,index=df.index)

def agg(g,p=''):
    wc=pick_col(g,'week'); games=int(pd.to_numeric(g[wc],errors='coerce').dropna().nunique()) if wc else int(num(g,'games').sum())
    return {
    p+'games':games,p+'pass_att':int(num(g,'attempts','passing_attempts','pass_attempts').sum()),p+'pass_comp':int(num(g,'completions','passing_completions').sum()),
    p+'pass_yards':int(num(g,'passing_yards','pass_yards').sum()),p+'pass_td':int(num(g,'passing_tds','passing_touchdowns','pass_tds').sum()),
    p+'pass_int':int(num(g,'interceptions','passing_interceptions').sum()),p+'rush_att':int(num(g,'carries','rushing_attempts').sum()),
    p+'rush_yards':int(num(g,'rushing_yards').sum()),p+'rush_td':int(num(g,'rushing_tds','rushing_touchdowns').sum()),p+'targets':int(num(g,'targets').sum()),
    p+'receptions':int(num(g,'receptions').sum()),p+'rec_yards':int(num(g,'receiving_yards').sum()),p+'rec_td':int(num(g,'receiving_tds','receiving_touchdowns').sum()),
    p+'sacks':float(num(g,'sacks','def_sacks','defensive_sacks').sum()),p+'tackles':int(num(g,'tackles','def_tackles','def_tackles_combined','defensive_tackles').sum()),
    p+'tfl':int(num(g,'tackles_for_loss','def_tackles_for_loss','tfl').sum()),p+'forced_fumbles':int(num(g,'sack_fumbles','forced_fumbles','def_fumbles_forced').sum()),
    p+'fumble_recoveries':int(num(g,'fumble_recoveries','def_fumble_recoveries').sum()),p+'def_interceptions':int(num(g,'def_interceptions','defensive_interceptions').sum()),
    p+'pressures':int(num(g,'pressures','def_pressures').sum()),p+'pass_breakups':int(num(g,'pass_defended','passes_defended','def_pass_defended','pass_breakups').sum()),
    p+'fg_att':int(num(g,'fg_attempts','field_goal_attempts').sum()),p+'fg_made':int(num(g,'fg_made','field_goals_made').sum()),p+'punts':int(num(g,'punts').sum()),
    p+'punt_yards':int(num(g,'punting_yards','punt_yards').sum()),p+'kick_returns':int(num(g,'kickoff_returns','kick_returns').sum()),
    p+'kick_return_yards':int(num(g,'kickoff_return_yards','kick_return_yards').sum()),p+'kick_return_td':int(num(g,'kickoff_return_tds','kick_return_tds').sum()),
    p+'punt_returns':int(num(g,'punt_returns').sum()),p+'punt_return_yards':int(num(g,'punt_return_yards').sum()),p+'punt_return_td':int(num(g,'punt_return_tds').sum())}

def main():
    targets=pd.read_csv(TARGETS)
    assert len(targets)==949 and targets.player_id.nunique()==949 and targets.player_name.nunique()==949
    assert int(targets.iloc[0].player_id)==15313 and int(targets.iloc[-1].player_id)==21841
    players=get_csv(PLAYERS_URL)
    gc=pick_col(players,'gsis_id','player_id'); pc=pick_col(players,'position','position_group')
    ncs=[c for c in ['display_name','full_name','football_name','short_name','name'] if c in players.columns]
    idx={}
    for i,r in players.iterrows():
        for c in ncs:
            n=norm(r.get(c));
            if n: idx.setdefault(n,set()).add(i)
    rows=[]; mapped=set(); bygsis={}
    for rank,t in targets.reset_index(drop=True).iterrows():
        cand=list(idx.get(norm(t.player_name),set())); status='AUTO_EXACT'
        if len(cand)>1 and pc:
            allowed=APP_POS_TO_NFL.get(str(t.position),{str(t.position)})
            narrowed=[i for i in cand if str(players.at[i,pc]).upper() in allowed]
            if len(narrowed)==1: cand=narrowed; status='AUTO_NAME_POSITION'
        if len(cand)==1:
            g=str(players.at[cand[0],gc]) if pd.notna(players.at[cand[0],gc]) else ''
            if g and g.lower()!='nan':
                mapped.add(g); bygsis[g]={'rank':rank+1001,'internal_player_id':int(t.player_id),'player_name':t.player_name,'position':t.position}
                rows.append([rank+1001,int(t.player_id),t.player_name,t.position,g,status,'']); continue
        rows.append([rank+1001,int(t.player_id),t.player_name,t.position,'','REVIEW' if cand else 'MISSING',f'candidate_count={len(cand)}'])
    mapping=pd.DataFrame(rows,columns=['rank','internal_player_id','player_name','position','gsis_id','mapping_status','note'])
    mapping.to_csv(OUT/'remaining949_player_mapping.csv',index=False)

    wp=[]; rp=[]; dla=[]
    for y in YEARS:
        try:
            s=get_csv(STATS_URL.format(year=y)); sid=pick_col(s,'player_id','gsis_id')
            sf=s[s[sid].astype(str).isin(mapped)].copy() if sid else pd.DataFrame()
            if not sf.empty: sf['_year']=y; sf['_gsis']=sf[sid].astype(str); wp.append(sf)
            dla.append([y,'stats','OK',len(s)])
        except Exception as e: dla.append([y,'stats','ERROR',str(e)])
        try:
            r=get_csv(ROSTER_URL.format(year=y)); rid=pick_col(r,'gsis_id','player_id')
            rf=r[r[rid].astype(str).isin(mapped)].copy() if rid else pd.DataFrame()
            if not rf.empty: rf['_year']=y; rf['_gsis']=rf[rid].astype(str); rp.append(rf)
            dla.append([y,'roster','OK',len(r)])
        except Exception as e: dla.append([y,'roster','ERROR',str(e)])
    dl=pd.DataFrame(dla,columns=['year','dataset','status','detail']); dl.to_csv(OUT/'download_audit.csv',index=False)
    assert (dl.status=='OK').all(), dl[dl.status!='OK'].to_dict('records')
    stats=pd.concat(wp,ignore_index=True) if wp else pd.DataFrame(); rosters=pd.concat(rp,ignore_index=True) if rp else pd.DataFrame()
    records={}
    if not rosters.empty:
        tc=pick_col(rosters,'team','team_abbr','recent_team')
        for (g,y,team),_ in rosters.groupby(['_gsis','_year',tc],dropna=False):
            if g not in bygsis: continue
            t=bygsis[g]; team='' if pd.isna(team) else str(team); key=(t['internal_player_id'],int(y),team)
            rec={c:0 for c in MASTER_COLS}; rec.update({'year':int(y),'player_name':t['player_name'],'position':t['position'],'team':team,'source':'nflverse weekly stats + season roster; remaining949'})
            records[key]=rec
    if not stats.empty:
        tc=pick_col(stats,'recent_team','team','team_abbr'); sc=pick_col(stats,'season_type')
        if not sc: stats['_stype']='REG'; sc='_stype'
        for (g,y,st,team),grp in stats.groupby(['_gsis','_year',sc,tc],dropna=False):
            if g not in bygsis: continue
            t=bygsis[g]; team='' if pd.isna(team) else str(team); key=(t['internal_player_id'],int(y),team)
            if key not in records:
                rec={c:0 for c in MASTER_COLS}; rec.update({'year':int(y),'player_name':t['player_name'],'position':t['position'],'team':team,'source':'nflverse weekly player stats; remaining949'}); records[key]=rec
            records[key].update(agg(grp,'post_' if str(st).upper().startswith('POST') else ''))
    bulk=pd.DataFrame(list(records.values()))
    for c in MASTER_COLS:
        if c not in bulk.columns: bulk[c]=0
    if not bulk.empty: bulk=bulk[MASTER_COLS].sort_values(['player_name','year','team']).reset_index(drop=True)
    bulk.to_csv(OUT/'remaining949_historical_stats_bulk.csv',index=False)
    audits=[]
    for i,t in targets.reset_index(drop=True).iterrows():
        m=mapping[mapping.internal_player_id.eq(int(t.player_id))].iloc[0]
        n=int((bulk.player_name.astype(str)==str(t.player_name)).sum()) if not bulk.empty else 0
        status='NEEDS_MAPPING_REVIEW' if m.mapping_status in ['MISSING','REVIEW'] else ('NO_PRE2026_HISTORY_OR_SOURCE_GAP' if n==0 else 'BULK_READY')
        audits.append([i+1001,int(t.player_id),t.player_name,t.position,m.gsis_id,m.mapping_status,n,status])
    audit=pd.DataFrame(audits,columns=['rank','internal_player_id','player_name','position','gsis_id','mapping_status','historical_rows','status'])
    audit.to_csv(OUT/'remaining949_audit.csv',index=False)
    bdir=OUT/'blocks'; bdir.mkdir(exist_ok=True)
    for b in range(95): audit.iloc[b*10:min((b+1)*10,949)].to_csv(bdir/f'block_{b+101:03d}_audit.csv',index=False)
    summary={'targets':949,'unique_ids':targets.player_id.nunique(),'unique_names':targets.player_name.nunique(),'mapped':int((~mapping.mapping_status.isin(['MISSING','REVIEW'])).sum()),'mapping_review':int((mapping.mapping_status=='REVIEW').sum()),'mapping_missing':int((mapping.mapping_status=='MISSING').sum()),'historical_rows':len(bulk),'bulk_ready':int((audit.status=='BULK_READY').sum()),'no_history_or_gap':int((audit.status=='NO_PRE2026_HISTORY_OR_SOURCE_GAP').sum()),'blocks':95}
    (OUT/'remaining949_summary.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n')
    print(summary)

if __name__=='__main__': main()
