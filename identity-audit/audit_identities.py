from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "historical-import"
OUT = ROOT / "identity-audit" / "output"
OUT.mkdir(parents=True, exist_ok=True)

PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
ROSTER_URL = "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{year}.csv"
ROSTER_YEARS = range(2018, 2027)

MAPPING_FILES = [
    HIST / "output" / "first1000_player_mapping_final.csv",
    HIST / "output_remaining949" / "remaining949_player_mapping_final.csv",
]

APP_POS_TO_NFL = {
    "QB": {"QB"},
    "HB": {"RB", "HB"},
    "FB": {"FB", "RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "LT": {"LT", "T", "OT", "OL"},
    "RT": {"RT", "T", "OT", "OL"},
    "LG": {"LG", "G", "OG", "OL"},
    "RG": {"RG", "G", "OG", "OL"},
    "C": {"C", "OL"},
    "LEDG": {"DE", "EDGE", "ED", "OLB", "LB", "DL"},
    "REDG": {"DE", "EDGE", "ED", "OLB", "LB", "DL"},
    "DT": {"DT", "NT", "DL"},
    "MIKE": {"LB", "ILB", "MLB"},
    "WILL": {"LB", "OLB", "ILB"},
    "SAM": {"LB", "OLB", "ILB"},
    "CB": {"CB", "DB"},
    "FS": {"S", "SAF", "FS", "DB"},
    "SS": {"S", "SAF", "SS", "DB"},
    "K": {"K"},
    "P": {"P"},
    "LS": {"LS"},
}


def norm(v: object) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def fetch_csv(url: str, timeout: int = 120) -> pd.DataFrame:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), low_memory=False)


def first_col(df: pd.DataFrame, *names: str) -> str | None:
    return next((n for n in names if n in df.columns), None)


def clean_year(v: object) -> int | None:
    try:
        if pd.isna(v):
            return None
        y = int(float(v))
        return y if 1900 <= y <= 2100 else None
    except Exception:
        return None


def clean_text(v: object) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def main() -> None:
    mappings = pd.concat([pd.read_csv(p) for p in MAPPING_FILES], ignore_index=True)
    assert len(mappings) == 1949, len(mappings)
    assert mappings["internal_player_id"].nunique() == 1949
    assert mappings["rank"].nunique() == 1949

    players = fetch_csv(PLAYERS_URL)
    gsis_col = first_col(players, "gsis_id", "player_id")
    if not gsis_col:
        raise RuntimeError("nflverse players.csv has no GSIS/player id column")
    players["_gsis"] = players[gsis_col].map(clean_text)

    name_cols = [c for c in ["display_name", "full_name", "football_name", "short_name", "name"] if c in players.columns]
    if not name_cols:
        raise RuntimeError("nflverse players.csv has no usable name column")
    pos_cols = [c for c in ["position", "position_group"] if c in players.columns]
    latest_cols = [c for c in ["latest_season", "last_season", "last_year", "season"] if c in players.columns]
    first_cols = [c for c in ["first_season", "rookie_season", "entry_year", "draft_year"] if c in players.columns]

    by_gsis: dict[str, dict] = {}
    name_index: dict[str, set[str]] = {}
    for _, r in players.iterrows():
        gsis = clean_text(r.get("_gsis"))
        if not gsis:
            continue
        names = {clean_text(r.get(c)) for c in name_cols if clean_text(r.get(c))}
        norms = {norm(n) for n in names if norm(n)}
        positions = {clean_text(r.get(c)).upper() for c in pos_cols if clean_text(r.get(c))}
        latest = max((y for c in latest_cols if (y := clean_year(r.get(c))) is not None), default=None)
        first = min((y for c in first_cols if (y := clean_year(r.get(c))) is not None), default=None)
        by_gsis[gsis] = {
            "gsis": gsis,
            "names": sorted(names),
            "norms": norms,
            "positions": positions,
            "latest_season": latest,
            "first_season": first,
        }
        for n in norms:
            name_index.setdefault(n, set()).add(gsis)

    roster_last: dict[str, int] = {}
    roster_first: dict[str, int] = {}
    roster_positions: dict[str, set[str]] = {}
    roster_teams: dict[str, dict[int, set[str]]] = {}
    download_rows = []

    for year in ROSTER_YEARS:
        try:
            r = fetch_csv(ROSTER_URL.format(year=year))
            rid = first_col(r, "gsis_id", "player_id")
            pcol = first_col(r, "position", "position_group")
            tcol = first_col(r, "team", "team_abbr", "recent_team")
            if not rid:
                raise RuntimeError("roster has no GSIS/player id column")
            for _, rr in r.iterrows():
                g = clean_text(rr.get(rid))
                if not g:
                    continue
                roster_last[g] = max(year, roster_last.get(g, year))
                roster_first[g] = min(year, roster_first.get(g, year))
                if pcol:
                    p = clean_text(rr.get(pcol)).upper()
                    if p:
                        roster_positions.setdefault(g, set()).add(p)
                if tcol:
                    team = clean_text(rr.get(tcol))
                    if team:
                        roster_teams.setdefault(g, {}).setdefault(year, set()).add(team)
            download_rows.append([year, "OK", len(r)])
        except Exception as exc:
            # 2026 may not exist yet in a given nflverse release. The audit remains valid
            # with prior seasons, so record rather than silently ignoring the gap.
            download_rows.append([year, "ERROR", str(exc)])

    pd.DataFrame(download_rows, columns=["year", "status", "detail"]).to_csv(OUT / "roster_download_audit.csv", index=False)

    def pos_match(app_pos: str, gsis: str) -> bool:
        allowed = APP_POS_TO_NFL.get(str(app_pos).upper(), {str(app_pos).upper()})
        observed = set(by_gsis.get(gsis, {}).get("positions", set())) | roster_positions.get(gsis, set())
        return bool(allowed & observed) if observed else False

    def activity_year(gsis: str) -> int | None:
        vals = [roster_last.get(gsis), by_gsis.get(gsis, {}).get("latest_season")]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    def candidate_score(target_name: str, app_pos: str, gsis: str) -> int:
        meta = by_gsis.get(gsis, {})
        score = 0
        if norm(target_name) in meta.get("norms", set()):
            score += 100
        if pos_match(app_pos, gsis):
            score += 60
        ay = activity_year(gsis)
        if ay is not None:
            score += max(0, min(40, (ay - 2018) * 5))
        if roster_last.get(gsis) == 2026:
            score += 25
        elif roster_last.get(gsis) == 2025:
            score += 20
        return score

    audit_rows = []
    suggestion_rows = []

    for _, m in mappings.sort_values("rank").iterrows():
        target_name = clean_text(m["player_name"])
        app_pos = clean_text(m["position"]).upper()
        mapped = clean_text(m["gsis_id"])
        mapped_meta = by_gsis.get(mapped)
        candidates = sorted(name_index.get(norm(target_name), set()))
        compatible = [g for g in candidates if pos_match(app_pos, g)]

        scored = sorted(
            [(candidate_score(target_name, app_pos, g), activity_year(g) or 0, g) for g in candidates],
            reverse=True,
        )
        best_score, best_active, best = scored[0] if scored else (0, 0, "")
        mapped_score = candidate_score(target_name, app_pos, mapped) if mapped_meta else -1
        mapped_active = activity_year(mapped) if mapped_meta else None
        mapped_name_ok = bool(mapped_meta and norm(target_name) in mapped_meta.get("norms", set()))
        mapped_pos_ok = bool(mapped_meta and pos_match(app_pos, mapped))

        status = "PASS"
        reason = "mapped identity is the best/only compatible exact-name candidate"

        if not mapped:
            status = "FAIL_MISSING_GSIS"
            reason = "mapping has no GSIS id"
        elif not mapped_meta:
            status = "FAIL_GSIS_NOT_IN_PLAYERS"
            reason = "mapped GSIS id is absent from current nflverse players.csv"
        elif not mapped_name_ok:
            status = "FAIL_NAME_MISMATCH"
            reason = "mapped GSIS player names do not normalize to target name"
        elif not mapped_pos_ok:
            if compatible:
                status = "FAIL_POSITION_MISMATCH"
                reason = "mapped identity position is incompatible while same-name compatible candidate exists"
            else:
                status = "REVIEW_POSITION"
                reason = "mapped identity position is incompatible and no clearly compatible same-name candidate was found"
        elif best and best != mapped:
            gap = best_score - mapped_score
            best_pos_ok = pos_match(app_pos, best)
            ma = mapped_active or 0
            ba = best_active or 0
            if best_pos_ok and (ba - ma >= 3) and gap >= 15:
                status = "FAIL_NAMESAKE_RECENCY"
                reason = f"same-name compatible candidate is materially newer ({ba} vs {ma})"
            elif gap >= 30:
                status = "FAIL_NAMESAKE_BETTER_MATCH"
                reason = f"same-name candidate has materially stronger identity score (+{gap})"
            else:
                status = "REVIEW_NAMESAKE"
                reason = f"multiple plausible same-name identities; best candidate score gap={gap}"
        elif len(compatible) > 1:
            # Even if mapped is currently best, keep close same-position namesakes visible.
            second = next((x for x in scored if x[2] != mapped and pos_match(app_pos, x[2])), None)
            if second and mapped_score - second[0] < 15:
                status = "REVIEW_NAMESAKE"
                reason = f"multiple close same-name/same-position candidates; score gap={mapped_score-second[0]}"

        best_meta = by_gsis.get(best, {}) if best else {}
        mapped_teams_2026 = ";".join(sorted(roster_teams.get(mapped, {}).get(2026, set())))
        mapped_teams_2025 = ";".join(sorted(roster_teams.get(mapped, {}).get(2025, set())))
        best_teams_2026 = ";".join(sorted(roster_teams.get(best, {}).get(2026, set()))) if best else ""
        best_teams_2025 = ";".join(sorted(roster_teams.get(best, {}).get(2025, set()))) if best else ""

        row = {
            "rank": int(m["rank"]),
            "internal_player_id": int(m["internal_player_id"]),
            "player_name": target_name,
            "app_position": app_pos,
            "mapped_gsis_id": mapped,
            "mapping_status_before": clean_text(m.get("mapping_status", "")),
            "identity_status": status,
            "reason": reason,
            "name_candidate_count": len(candidates),
            "compatible_candidate_count": len(compatible),
            "mapped_score": mapped_score,
            "mapped_positions": ";".join(sorted((mapped_meta or {}).get("positions", set()) | roster_positions.get(mapped, set()))),
            "mapped_first_season": (mapped_meta or {}).get("first_season"),
            "mapped_latest_season": (mapped_meta or {}).get("latest_season"),
            "mapped_last_roster_year": roster_last.get(mapped),
            "mapped_team_2026": mapped_teams_2026,
            "mapped_team_2025": mapped_teams_2025,
            "best_candidate_gsis": best,
            "best_candidate_names": ";".join(best_meta.get("names", [])),
            "best_candidate_positions": ";".join(sorted(best_meta.get("positions", set()) | roster_positions.get(best, set()))) if best else "",
            "best_candidate_first_season": best_meta.get("first_season") if best else None,
            "best_candidate_latest_season": best_meta.get("latest_season") if best else None,
            "best_candidate_last_roster_year": roster_last.get(best) if best else None,
            "best_candidate_team_2026": best_teams_2026,
            "best_candidate_team_2025": best_teams_2025,
            "best_candidate_score": best_score,
        }
        audit_rows.append(row)

        if status.startswith("FAIL_") and best and best != mapped and pos_match(app_pos, best):
            suggestion_rows.append({
                "rank": int(m["rank"]),
                "internal_player_id": int(m["internal_player_id"]),
                "player_name": target_name,
                "position": app_pos,
                "old_gsis_id": mapped,
                "suggested_gsis_id": best,
                "reason": reason,
                "old_activity_year": mapped_active,
                "suggested_activity_year": activity_year(best),
                "old_score": mapped_score,
                "suggested_score": best_score,
            })

    audit = pd.DataFrame(audit_rows).sort_values("rank")
    suspects = audit[audit.identity_status != "PASS"].copy()
    suggestions = pd.DataFrame(suggestion_rows)

    audit.to_csv(OUT / "full1949_identity_audit.csv", index=False)
    suspects.to_csv(OUT / "full1949_identity_suspects.csv", index=False)
    suggestions.to_csv(OUT / "full1949_identity_suggested_overrides.csv", index=False)

    counts = audit.identity_status.value_counts().to_dict()
    summary = {
        "targets": len(audit),
        "unique_internal_ids": audit.internal_player_id.nunique(),
        "pass": int((audit.identity_status == "PASS").sum()),
        "suspects_total": len(suspects),
        "clear_failures": int(audit.identity_status.str.startswith("FAIL_").sum()),
        "manual_reviews": int(audit.identity_status.str.startswith("REVIEW_").sum()),
        "suggested_overrides": len(suggestions),
        "roster_download_errors": sum(1 for _, s, _ in download_rows if s != "OK"),
    }
    for k, v in sorted(counts.items()):
        summary[f"status_{k}"] = int(v)

    # Regression guard for the already-confirmed bad Chris Jones mapping.
    cj = audit[(audit.player_name == "Chris Jones") & (audit.app_position == "DT")]
    if not cj.empty:
        cjrow = cj.iloc[0]
        summary["chris_jones_mapped_gsis"] = cjrow.mapped_gsis_id
        summary["chris_jones_identity_status"] = cjrow.identity_status
        summary["chris_jones_best_candidate_gsis"] = cjrow.best_candidate_gsis

    (OUT / "full1949_identity_summary.txt").write_text(
        "\n".join(f"{k}={v}" for k, v in summary.items()) + "\n",
        encoding="utf-8",
    )
    print(summary)


if __name__ == "__main__":
    main()
