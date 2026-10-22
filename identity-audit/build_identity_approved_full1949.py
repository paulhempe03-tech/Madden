from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / 'historical-import'
OUT = ROOT / 'identity-audit' / 'output'
OUT.mkdir(parents=True, exist_ok=True)

BATCHES = [
    (
        'first1000',
        HIST / 'output' / 'first1000_historical_stats_final.csv',
        HIST / 'output' / 'first1000_player_mapping_final.csv',
        HIST / 'output' / 'first1000_audit_final.csv',
    ),
    (
        'remaining949',
        HIST / 'output_remaining949' / 'remaining949_historical_stats_final.csv',
        HIST / 'output_remaining949' / 'remaining949_player_mapping_final.csv',
        HIST / 'output_remaining949' / 'remaining949_audit_final.csv',
    ),
]

identity = pd.read_csv(OUT / 'full1949_identity_audit_adjudicated.csv')
assert len(identity) == 1949
assert (identity.final_identity_status != 'FINAL_UNRESOLVED').all()

full_parts = []
coverage_parts = []
for batch, stats_path, map_path, audit_path in BATCHES:
    stats = pd.read_csv(stats_path, low_memory=False)
    mapping = pd.read_csv(map_path)
    audit = pd.read_csv(audit_path)

    assert mapping.internal_player_id.nunique() == len(mapping)
    assert mapping.player_name.nunique() == len(mapping), f'{batch}: target names not unique within batch'

    meta = mapping.set_index('player_name')[['rank','internal_player_id','gsis_id','position']]
    stats['internal_player_id'] = stats.player_name.map(meta.internal_player_id)
    stats['gsis_id'] = stats.player_name.map(meta.gsis_id)
    stats['rank'] = stats.player_name.map(meta['rank'])
    stats['source_batch'] = batch
    if stats.internal_player_id.isna().any():
        bad = stats[stats.internal_player_id.isna()].player_name.drop_duplicates().tolist()
        raise SystemExit(f'{batch}: history rows without internal id: {bad[:20]}')
    stats['internal_player_id'] = stats.internal_player_id.astype(int)
    stats['rank'] = stats['rank'].astype(int)
    full_parts.append(stats)

    cov = mapping[['rank','internal_player_id','player_name','position','gsis_id','mapping_status']].merge(
        audit[['internal_player_id','historical_rows','status']], on='internal_player_id', how='left'
    )
    cov['source_batch'] = batch
    coverage_parts.append(cov)

full = pd.concat(full_parts, ignore_index=True)
coverage = pd.concat(coverage_parts, ignore_index=True).sort_values('rank')

idcols = identity[['internal_player_id','final_identity_status','adjudication']]
coverage = coverage.merge(idcols, on='internal_player_id', how='left')

# Stable output order keeps direct player identity fields in front.
front = ['rank','internal_player_id','gsis_id','player_name','position','year','team','source','source_batch']
rest = [c for c in full.columns if c not in front]
full = full[front + rest].sort_values(['rank','year','team']).reset_index(drop=True)

out_csv = OUT / 'nfl_historical_player_stats_1999_2025_full1949_identity_approved.csv'
full.to_csv(out_csv, index=False)
coverage.to_csv(OUT / 'full1949_player_coverage_identity_approved.csv', index=False)

source_gap = int((coverage.status == 'SOURCE_GAP').sum())
unresolved_mapping = int(coverage.mapping_status.isin(['MISSING','REVIEW']).sum())
identity_unresolved = int((coverage.final_identity_status == 'FINAL_UNRESOLVED').sum())
dups = int(full.duplicated(['internal_player_id','year','team']).sum())
players_with_history = int(full.internal_player_id.nunique())
no_history = int((coverage.historical_rows.fillna(0) == 0).sum())

# Same display name can legitimately refer to different current players; internal IDs must preserve them.
name_id_counts = coverage.groupby('player_name').internal_player_id.nunique()
name_collisions = name_id_counts[name_id_counts > 1]

cj = full[(full.internal_player_id == 17676) & (full.player_name == 'Chris Jones')]
if cj.empty:
    raise SystemExit('Chris Jones history missing after identity repair')
cj_year_min = int(cj.year.min())
cj_year_max = int(cj.year.max())
cj_teams = ';'.join(sorted(cj.team.dropna().astype(str).unique()))
cj_bad_pre2016 = int((cj.year < 2016).sum())

summary = {
    'targets': len(coverage),
    'unique_internal_ids': coverage.internal_player_id.nunique(),
    'historical_rows': len(full),
    'players_with_pre2026_history': players_with_history,
    'no_pre2026_history': no_history,
    'source_gap': source_gap,
    'unresolved_mapping': unresolved_mapping,
    'identity_unresolved': identity_unresolved,
    'duplicate_internal_player_year_team_rows': dups,
    'display_names_shared_by_multiple_internal_ids': len(name_collisions),
    'chris_jones_rows': len(cj),
    'chris_jones_year_min': cj_year_min,
    'chris_jones_year_max': cj_year_max,
    'chris_jones_teams': cj_teams,
    'chris_jones_pre2016_rows': cj_bad_pre2016,
}
(OUT / 'full1949_identity_approved_dataset_summary.txt').write_text(
    '\n'.join(f'{k}={v}' for k,v in summary.items()) + '\n', encoding='utf-8'
)
print(summary)

assert summary['targets'] == 1949
assert summary['unique_internal_ids'] == 1949
assert summary['source_gap'] == 0
assert summary['unresolved_mapping'] == 0
assert summary['identity_unresolved'] == 0
assert summary['duplicate_internal_player_year_team_rows'] == 0
assert summary['chris_jones_pre2016_rows'] == 0
assert summary['chris_jones_year_min'] == 2016
assert summary['chris_jones_year_max'] == 2025
