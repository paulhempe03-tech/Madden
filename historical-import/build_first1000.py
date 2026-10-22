from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
TARGETS = ROOT / "targets_first1000.csv"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

YEARS = range(1999, 2026)
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv"
ROSTER_URL = "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{year}.csv"

MASTER_COLS = [
    "year","player_name","position","team","source","games",
    "pass_att","pass_comp","pass_yards","pass_td","pass_int",
    "rush_att","rush_yards","rush_td","targets","receptions","rec_yards","rec_td",
    "sacks","tackles","tfl","forced_fumbles","fumble_recoveries","def_interceptions",
    "pressures","pass_breakups","fg_att","fg_made","punts","punt_yards",
    "kick_returns","kick_return_yards","kick_return_td","punt_returns","punt_return_yards","punt_return_td",
    "post_games","post_pass_att","post_pass_comp","post_pass_yards","post_pass_td","post_pass_int",
    "post_rush_att","post_rush_yards","post_rush_td","post_targets","post_receptions","post_rec_yards","post_rec_td",
    "post_sacks","post_tackles","post_tfl","post_forced_fumbles","post_fumble_recoveries","post_def_interceptions",
    "post_pressures","post_pass_breakups","post_fg_att","post_fg_made","post_punts","post_punt_yards",
    "post_kick_returns","post_kick_return_yards","post_kick_return_td","post_punt_returns","post_punt_return_yards","post_punt_return_td"
]

APP_POS_TO_NFL = {
    "HB": {"RB"}, "FB": {"FB"}, "WR": {"WR"}, "TE": {"TE"}, "QB": {"QB"},
    "LT": {"OT","T","LT"}, "RT": {"OT","T","RT"}, "LG": {"OG","G","LG"}, "RG": {"OG","G","RG"}, "C": {"C"},
    "LEDG": {"DE","EDGE","OLB"}, "REDG": {"DE","EDGE","OLB"}, "DT": {"DT","NT"},
    "MIKE": {"LB","ILB","MLB"}, "WILL": {"LB","OLB"}, "SAM": {"LB","OLB"},
    "CB": {"CB"}, "FS": {"S","FS"}, "SS": {"S","SS"}, "K": {"K"}, "P": {"P"}, "LS": {"LS"},
}


def norm_name(v: object) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("’", "'")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def get_csv(url: str, timeout: int = 90) -> pd.DataFrame:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), low_memory=False)


def pick_col(df: pd.DataFrame, *candidates: str):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def num_series(df: pd.DataFrame, *candidates: str) -> pd.Series:
    c = pick_col(df, *candidates)
    if not c:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[c], errors="coerce").fillna(0)


def aggregate_group(g: pd.DataFrame, prefix: str = "") -> dict:
    # games: count distinct weekly appearances if week exists, else sum games if present
    week_col = pick_col(g, "week")
    if week_col:
        games = int(pd.to_numeric(g[week_col], errors="coerce").dropna().nunique())
    else:
        games = int(num_series(g, "games").sum())
    d = {
        f"{prefix}games": games,
        f"{prefix}pass_att": int(num_series(g,"attempts","passing_attempts","pass_attempts").sum()),
        f"{prefix}pass_comp": int(num_series(g,"completions","passing_completions").sum()),
        f"{prefix}pass_yards": int(num_series(g,"passing_yards","pass_yards").sum()),
        f"{prefix}pass_td": int(num_series(g,"passing_tds","passing_touchdowns","pass_tds").sum()),
        f"{prefix}pass_int": int(num_series(g,"interceptions","passing_interceptions").sum()),
        f"{prefix}rush_att": int(num_series(g,"carries","rushing_attempts").sum()),
        f"{prefix}rush_yards": int(num_series(g,"rushing_yards").sum()),
        f"{prefix}rush_td": int(num_series(g,"rushing_tds","rushing_touchdowns").sum()),
        f"{prefix}targets": int(num_series(g,"targets").sum()),
        f"{prefix}receptions": int(num_series(g,"receptions").sum()),
        f"{prefix}rec_yards": int(num_series(g,"receiving_yards").sum()),
        f"{prefix}rec_td": int(num_series(g,"receiving_tds","receiving_touchdowns").sum()),
        f"{prefix}sacks": float(num_series(g,"sacks","def_sacks","defensive_sacks").sum()),
        f"{prefix}tackles": int(num_series(g,"tackles","def_tackles","def_tackles_combined","defensive_tackles").sum()),
        f"{prefix}tfl": int(num_series(g,"tackles_for_loss","def_tackles_for_loss","tfl").sum()),
        f"{prefix}forced_fumbles": int(num_series(g,"sack_fumbles","forced_fumbles","def_fumbles_forced").sum()),
        f"{prefix}fumble_recoveries": int(num_series(g,"fumble_recoveries","def_fumble_recoveries").sum()),
        f"{prefix}def_interceptions": int(num_series(g,"def_interceptions","defensive_interceptions").sum()),
        f"{prefix}pressures": int(num_series(g,"pressures","def_pressures").sum()),
        f"{prefix}pass_breakups": int(num_series(g,"pass_defended","passes_defended","def_pass_defended","pass_breakups").sum()),
        f"{prefix}fg_att": int(num_series(g,"fg_attempts","field_goal_attempts").sum()),
        f"{prefix}fg_made": int(num_series(g,"fg_made","field_goals_made").sum()),
        f"{prefix}punts": int(num_series(g,"punts").sum()),
        f"{prefix}punt_yards": int(num_series(g,"punting_yards","punt_yards").sum()),
        f"{prefix}kick_returns": int(num_series(g,"kickoff_returns","kick_returns").sum()),
        f"{prefix}kick_return_yards": int(num_series(g,"kickoff_return_yards","kick_return_yards").sum()),
        f"{prefix}kick_return_td": int(num_series(g,"kickoff_return_tds","kick_return_tds").sum()),
        f"{prefix}punt_returns": int(num_series(g,"punt_returns").sum()),
        f"{prefix}punt_return_yards": int(num_series(g,"punt_return_yards").sum()),
        f"{prefix}punt_return_td": int(num_series(g,"punt_return_tds").sum()),
    }
    return d


def main():
    targets = pd.read_csv(TARGETS)
    if len(targets) != 1000:
        raise SystemExit(f"Expected exactly 1000 targets, got {len(targets)}")

    players = get_csv(PLAYERS_URL)
    gsis_col = pick_col(players, "gsis_id", "player_id")
    pos_col = pick_col(players, "position", "position_group")
    name_cols = [c for c in ["display_name","full_name","football_name","short_name","name"] if c in players.columns]
    if not gsis_col or not name_cols:
        raise SystemExit(f"players.csv schema unexpected: {players.columns.tolist()}")

    name_index: dict[str, set[int]] = {}
    for i,row in players.iterrows():
        for c in name_cols:
            n = norm_name(row.get(c))
            if n:
                name_index.setdefault(n,set()).add(i)

    map_rows=[]
    mapped_gsis=set()
    target_by_gsis={}
    for rank,t in targets.reset_index(drop=True).iterrows():
        n=norm_name(t.player_name)
        cand=list(name_index.get(n,set()))
        status="AUTO_EXACT"
        if len(cand)>1 and pos_col:
            allowed=APP_POS_TO_NFL.get(str(t.position),{str(t.position)})
            narrowed=[i for i in cand if str(players.at[i,pos_col]).upper() in allowed]
            if len(narrowed)==1:
                cand=narrowed; status="AUTO_NAME_POSITION"
        if len(cand)==1:
            prow=players.loc[cand[0]]
            gsis=str(prow[gsis_col]) if pd.notna(prow[gsis_col]) else ""
            if gsis and gsis.lower()!="nan":
                mapped_gsis.add(gsis)
                target_by_gsis[gsis]={"rank":rank+1,"internal_player_id":int(t.player_id),"player_name":t.player_name,"position":t.position}
                map_rows.append([rank+1,int(t.player_id),t.player_name,t.position,gsis,status,""])
                continue
        map_rows.append([rank+1,int(t.player_id),t.player_name,t.position,"","REVIEW" if cand else "MISSING",f"candidate_count={len(cand)}"])

    mapping=pd.DataFrame(map_rows,columns=["rank","internal_player_id","player_name","position","gsis_id","mapping_status","note"])
    mapping.to_csv(OUT/"first1000_player_mapping.csv",index=False)

    # Weekly stats preserve team splits. Accumulate only mapped targets.
    weekly_parts=[]
    roster_presence=[]
    download_audit=[]
    for year in YEARS:
        try:
            s=get_csv(STATS_URL.format(year=year))
            sid=pick_col(s,"player_id","gsis_id")
            if sid:
                sf=s[s[sid].astype(str).isin(mapped_gsis)].copy()
                if not sf.empty:
                    sf["_year"]=year
                    sf["_gsis"]=sf[sid].astype(str)
                    weekly_parts.append(sf)
            download_audit.append([year,"stats","OK",len(s)])
        except Exception as e:
            download_audit.append([year,"stats","ERROR",str(e)])

        try:
            r=get_csv(ROSTER_URL.format(year=year))
            rid=pick_col(r,"gsis_id","player_id")
            if rid:
                rf=r[r[rid].astype(str).isin(mapped_gsis)].copy()
                if not rf.empty:
                    rf["_year"]=year
                    rf["_gsis"]=rf[rid].astype(str)
                    roster_presence.append(rf)
            download_audit.append([year,"roster","OK",len(r)])
        except Exception as e:
            download_audit.append([year,"roster","ERROR",str(e)])

    pd.DataFrame(download_audit,columns=["year","dataset","status","detail"]).to_csv(OUT/"download_audit.csv",index=False)

    stats=pd.concat(weekly_parts,ignore_index=True) if weekly_parts else pd.DataFrame()
    rosters=pd.concat(roster_presence,ignore_index=True) if roster_presence else pd.DataFrame()

    records={}
    # Base season/team rows from roster presence so OL and zero-boxscore players survive.
    if not rosters.empty:
        teamc=pick_col(rosters,"team","team_abbr","recent_team")
        if teamc:
            for (gsis,year,team),g in rosters.groupby(["_gsis","_year",teamc],dropna=False):
                if gsis not in target_by_gsis: continue
                t=target_by_gsis[gsis]
                team="" if pd.isna(team) else str(team)
                key=(int(t["internal_player_id"]),int(year),team)
                rec={c:0 for c in MASTER_COLS}
                rec.update({"year":int(year),"player_name":t["player_name"],"position":t["position"],"team":team,
                            "source":"nflverse weekly stats + season roster; bulk first1000"})
                records[key]=rec

    if not stats.empty:
        teamc=pick_col(stats,"recent_team","team","team_abbr")
        stypec=pick_col(stats,"season_type")
        if not teamc:
            raise SystemExit("weekly stats have no team column")
        if not stypec:
            stats["_stype"]="REG"; stypec="_stype"
        for (gsis,year,stype,team),g in stats.groupby(["_gsis","_year",stypec,teamc],dropna=False):
            if gsis not in target_by_gsis: continue
            t=target_by_gsis[gsis]
            team="" if pd.isna(team) else str(team)
            key=(int(t["internal_player_id"]),int(year),team)
            if key not in records:
                rec={c:0 for c in MASTER_COLS}
                rec.update({"year":int(year),"player_name":t["player_name"],"position":t["position"],"team":team,
                            "source":"nflverse weekly player stats; bulk first1000"})
                records[key]=rec
            prefix="post_" if str(stype).upper().startswith("POST") else ""
            records[key].update(aggregate_group(g,prefix))

    bulk=pd.DataFrame(list(records.values()))
    for c in MASTER_COLS:
        if c not in bulk.columns: bulk[c]=0
    if not bulk.empty:
        bulk=bulk[MASTER_COLS].sort_values(["player_name","year","team"]).reset_index(drop=True)
    bulk.to_csv(OUT/"first1000_historical_stats_bulk.csv",index=False)

    # Target-level completion/audit; first 10 remain manual-master-authoritative downstream.
    hist_names=set(bulk.player_name.astype(str)) if not bulk.empty else set()
    audits=[]
    for rank,t in targets.reset_index(drop=True).iterrows():
        m=mapping[mapping.internal_player_id==int(t.player_id)].iloc[0]
        rows_n=int((bulk.player_name==t.player_name).sum()) if not bulk.empty else 0
        if rank < 10:
            status="KEEP_EXISTING_MANUAL_BLOCK001"
        elif m.mapping_status in ("MISSING","REVIEW"):
            status="NEEDS_MAPPING_REVIEW"
        elif rows_n==0:
            status="NO_PRE2026_HISTORY_OR_SOURCE_GAP"
        else:
            status="BULK_READY"
        audits.append([rank+1,int(t.player_id),t.player_name,t.position,m.gsis_id,m.mapping_status,rows_n,status])
    audit=pd.DataFrame(audits,columns=["rank","internal_player_id","player_name","position","gsis_id","mapping_status","historical_rows","status"])
    audit.to_csv(OUT/"first1000_audit.csv",index=False)

    # 100 checkpoint audits (10 players each)
    blocks=OUT/"blocks"; blocks.mkdir(exist_ok=True)
    for b in range(100):
        sub=audit.iloc[b*10:(b+1)*10].copy()
        sub.to_csv(blocks/f"block_{b+1:03d}_audit.csv",index=False)

    summary = [
        f"targets=1000",
        f"mapped={(~mapping.mapping_status.isin(['MISSING','REVIEW'])).sum()}",
        f"mapping_review={(mapping.mapping_status=='REVIEW').sum()}",
        f"mapping_missing={(mapping.mapping_status=='MISSING').sum()}",
        f"historical_rows={len(bulk)}",
        f"bulk_ready={(audit.status=='BULK_READY').sum()}",
        f"no_history_or_gap={(audit.status=='NO_PRE2026_HISTORY_OR_SOURCE_GAP').sum()}",
        f"manual_block001_preserved={(audit.status=='KEEP_EXISTING_MANUAL_BLOCK001').sum()}",
        f"blocks=100",
    ]
    (OUT/"first1000_summary.txt").write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("\n".join(summary))

if __name__ == "__main__":
    main()
