from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'identity-audit' / 'output'
HIST = ROOT / 'historical-import'

raw = pd.read_csv(OUT / 'full1949_identity_audit.csv')

def pairs_from(path: Path):
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return {
        (int(r.internal_player_id), str(r.gsis_id)): getattr(r, 'note', '')
        for r in df.itertuples(index=False)
    }

overrides = {}
overrides.update(pairs_from(HIST / 'mapping_overrides.csv'))
overrides.update(pairs_from(HIST / 'mapping_overrides_remaining949.csv'))

exc_path = ROOT / 'identity-audit' / 'verified_exceptions.csv'
exceptions = {}
if exc_path.exists():
    ex = pd.read_csv(exc_path)
    exceptions = {
        (int(r.internal_player_id), str(r.gsis_id)): (str(r.exception_type), str(r.note), str(r.evidence))
        for r in ex.itertuples(index=False)
    }

final_rows = []
for r in raw.itertuples(index=False):
    key = (int(r.internal_player_id), str(r.mapped_gsis_id))
    active = max(
        int(r.mapped_last_roster_year) if pd.notna(r.mapped_last_roster_year) else 0,
        int(r.mapped_latest_season) if pd.notna(r.mapped_latest_season) else 0,
    )
    raw_status = str(r.identity_status)
    final_status = 'FINAL_UNRESOLVED'
    adjudication = str(r.reason)
    evidence = ''

    if raw_status == 'PASS':
        final_status = 'FINAL_PASS_AUTO'
        adjudication = 'automated identity checks passed'
    elif key in exceptions:
        etype, note, evidence = exceptions[key]
        if active >= 2025:
            final_status = f'FINAL_PASS_{etype}'
            adjudication = note
    elif key in overrides and active >= 2025:
        note = str(overrides[key])
        # Historical override rows were manually resolved to a concrete current GSIS id.
        # Current/recent roster activity guards against accepting a stale namesake.
        if raw_status == 'FAIL_NAME_MISMATCH':
            final_status = 'FINAL_PASS_VERIFIED_ALIAS'
            adjudication = note
        elif raw_status == 'REVIEW_NAMESAKE':
            final_status = 'FINAL_PASS_VERIFIED_NAMESAKE'
            adjudication = note
        elif raw_status == 'REVIEW_POSITION':
            # Position-only disagreement needs an explicit exception, not just an alias override.
            final_status = 'FINAL_UNRESOLVED'
        elif raw_status.startswith('FAIL_'):
            # Do not let a prior override conceal a newly detected hard contradiction.
            final_status = 'FINAL_UNRESOLVED'

    d = r._asdict()
    d['final_identity_status'] = final_status
    d['adjudication'] = adjudication
    d['evidence'] = evidence
    final_rows.append(d)

final = pd.DataFrame(final_rows).sort_values('rank')
unresolved = final[final.final_identity_status == 'FINAL_UNRESOLVED'].copy()
final.to_csv(OUT / 'full1949_identity_audit_adjudicated.csv', index=False)
unresolved.to_csv(OUT / 'full1949_identity_unresolved.csv', index=False)

counts = final.final_identity_status.value_counts().to_dict()
summary = {
    'targets': len(final),
    'unique_internal_ids': final.internal_player_id.nunique(),
    'final_pass': int((final.final_identity_status != 'FINAL_UNRESOLVED').sum()),
    'final_unresolved': len(unresolved),
}
for k, v in sorted(counts.items()):
    summary[f'status_{k}'] = int(v)

# Critical regression checks.
cj = final[(final.player_name == 'Chris Jones') & (final.app_position == 'DT')]
if len(cj) != 1:
    raise SystemExit(f'Expected exactly one target Chris Jones DT row, found {len(cj)}')
cjr = cj.iloc[0]
summary['chris_jones_gsis'] = cjr.mapped_gsis_id
summary['chris_jones_final_status'] = cjr.final_identity_status
if str(cjr.mapped_gsis_id) != '00-0032762':
    raise SystemExit(f'Chris Jones regression: {cjr.mapped_gsis_id}')

# Distinct current Jaylon Jones identities must remain separate.
jj = final[final.player_name == 'Jaylon Jones']
summary['jaylon_jones_rows'] = len(jj)
summary['jaylon_jones_unique_gsis'] = jj.mapped_gsis_id.nunique()
if len(jj) != 2 or jj.mapped_gsis_id.nunique() != 2:
    raise SystemExit('Jaylon Jones identities collapsed or missing')

(OUT / 'full1949_identity_final_summary.txt').write_text(
    '\n'.join(f'{k}={v}' for k, v in summary.items()) + '\n', encoding='utf-8'
)
print(summary)

assert summary['targets'] == 1949
assert summary['unique_internal_ids'] == 1949
assert summary['final_unresolved'] == 0, unresolved[['rank','internal_player_id','player_name','mapped_gsis_id','identity_status','reason']].to_dict('records')
