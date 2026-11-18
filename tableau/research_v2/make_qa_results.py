"""Compare values copied from Tableau (Worksheet > Copy > Data of QA-only sheets) with the WP1/WP2 reference tables.
Usage: python tableau/research_v2/make_qa_results.py [repo_root]. Writes artifacts/research_v2/tableau/qa_results.csv. Counts exact; rates / shares compared at integer-scaled 1e-9 precision (tolerance 1e-6)."""
import pandas as pd, sys
from pathlib import Path
U = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]   # repo root
TAB = U / 'artifacts/research_v2/tableau'
D = TAB / 'displayed'; OUT = []
LAB = {'lt_50':'Under 50','50_249':'50-249','250_999':'250-999','1000_plus':'1,000 or more'}
def rd(f): return pd.read_csv(D/f, sep='\t', thousands=',')
def add(cid, sheet, src, ref, filt, scen, key, meas, exp, disp, tol):
    diff = abs(float(exp) - float(disp)); OUT.append(dict(check_id=cid, tableau_sheet=sheet, data_source=src, reference=ref, filters=filt,
        scenario=scen, key=key, measure=meas, expected=exp, displayed=disp, tolerance=tol, abs_diff=diff, result='PASS' if diff <= tol else 'FAIL'))
# ---- annual
ref = pd.read_csv(U/'artifacts/research_v2/annual/tableau_reference_totals.csv')
d = rd('qa_annual_by_year.tsv')
m = d.merge(ref, on=['year','scenario'], how='outer', indicator=True); assert (m._merge=='both').all(), 'annual year keys'
for _, r in m.iterrows():
    k = f"{r.year}"; s = r.scenario
    for meas, a, b, tol in [('establishment_year_count','Establishment-years','establishment_year_count',0), ('dart_case_count','Reported DART cases','dart_case_count',0),
                            ('hours_sum','Reported hours worked','hours_sum',0.5)]:
        add('A1','QA annual by year','annual_size_summary.csv','annual/tableau_reference_totals.csv','scenario param = row; no other filters',s,k,meas,r[b],r[a],tol)
    add('A1','QA annual by year','annual_size_summary.csv','annual/tableau_reference_totals.csv','scenario param = row; no other filters',s,k,'pooled_rate_200000*dart/hours',r.dart_rate_reference,r['QA rate x 1e9 (integer)']/1e9,1e-6)
a = pd.read_csv(U/'data/processed/research_v2/annual_size_summary.csv'); a['label'] = a.size_group.map(LAB)
d = rd('qa_annual_by_size.tsv'); d.columns = ['label','scenario','year','rate3','estyrs','rate9','cases','hours']
m = d.merge(a, on=['label','scenario','year']); assert len(m) == len(d) == len(a)
for _, r in m.iterrows():
    k = f"{r.year} | {r.label}"
    for meas, e, v, tol in [('establishment_year_count', r.establishment_year_count, r.estyrs, 0), ('dart_case_count', r.dart_case_count, r.cases, 0), ('hours_sum', r.hours_sum, r.hours, 0.5)]:
        add('A2','QA annual by size','annual_size_summary.csv','data/processed/research_v2/annual_size_summary.csv','scenario param = row',r.scenario,k,meas,e,v,tol)
    add('A2','QA annual by size','annual_size_summary.csv','recomputed 200000*SUM(dart)/SUM(hours) from source rows','scenario param = row',r.scenario,k,'pooled_rate',200000*r.dart_case_count/r.hours_sum,r.rate9/1e9,1e-6)
# ---- case
cref = pd.read_csv(U/'data/interim/wp3_provisional_case/audit/tableau_reference_totals.csv', dtype={'year':str})
cs = pd.read_csv(U/'data/interim/wp3_provisional_case/proc/case_pattern_summary.csv')
mlab = cs[['mechanism_group','mechanism_label']].drop_duplicates(); slab = cs[['soc_major_group','soc_major_label']].drop_duplicates()
def case_rows(cid, sheet, df, keycols, refdf, refkeys, filt):
    m = df.merge(refdf, left_on=keycols, right_on=refkeys, how='outer', indicator=True); assert (m._merge=='both').all(), cid
    for _, r in m.iterrows():
        k = ' | '.join(str(r[c]) for c in keycols if c != 'scenario'); s = r['scenario']
        for meas, e, v in [('case_report_count', r.case_report_count, r['Case reports']), ('dafw_days_sum', r.dafw_days_sum, r['Days-away numerator']),
                           ('dafw_days_known_report_count', r.dafw_days_known_report_count, r['Days-away denominator (reports with valid value)']),
                           ('djtr_days_sum', r.djtr_days_sum, r['Restricted days numerator']), ('djtr_days_known_report_count', r.djtr_days_known_report_count, r['Restricted days denominator (reports with valid value)'])]:
            add(cid, sheet, 'case_pattern_summary.csv', 'wp3_provisional_case/audit/tableau_reference_totals.csv', filt, s, k, meas, e, v, 0)
        add(cid, sheet, 'case_pattern_summary.csv', 'wp3_provisional_case/audit/tableau_reference_totals.csv', filt, s, k, 'mean_days_away', r.dafw_mean_days_per_known_report, r['QA mean days away x 1e9 (integer)']/1e9, 1e-6)
        add(cid, sheet, 'case_pattern_summary.csv', 'wp3_provisional_case/audit/tableau_reference_totals.csv', filt, s, k, 'mean_restricted_days', r.djtr_mean_days_per_known_report, r['QA mean restricted days x 1e9 (integer)']/1e9, 1e-6)
        if 'QA percent of reports x 1e9 (integer)' in r.index:
            add(cid, sheet, 'case_pattern_summary.csv', 'share of reports computed from reference counts (incl. Unknown/Other)', filt, s, k, 'percent_of_reports', r.case_report_count/r.tot, r['QA percent of reports x 1e9 (integer)']/1e9, 1e-6)
d = rd('qa_case_by_year.tsv'); d.columns = ['scenario','year','Case reports','Days-away denominator (reports with valid value)','Days-away numerator','QA mean days away x 1e9 (integer)','QA mean restricted days x 1e9 (integer)','Restricted days denominator (reports with valid value)','Restricted days numerator']
r1 = cref[cref.reference_level=='year_scenario'].query("year!='all'").copy(); r1['year'] = r1.year.astype(int)
case_rows('C1','QA case by year',d,['scenario','year'],r1,['scenario','year'],'year in {2023,2024}')
d = rd('qa_case_by_mechanism.tsv').rename(columns={'mechanism_label':'mech'}); r2 = cref[cref.reference_level=='year_mechanism_scenario'].copy(); r2['year']=r2.year.astype(int); r2 = r2.merge(mlab,on='mechanism_group')
r2['tot'] = r2.groupby(['scenario','year']).case_report_count.transform('sum'); d['mechanism_label']=d['mech']
case_rows('C2','QA case by mechanism',d,['mechanism_label','scenario','year'],r2,['mechanism_label','scenario','year'],'year in {2023,2024}')
d = rd('qa_case_by_occupation.tsv'); r3 = cref[cref.reference_level=='year_soc_scenario'].copy(); r3['year']=r3.year.astype(int); r3 = r3.merge(slab,on='soc_major_group')
case_rows('C3','QA case by occupation',d,['soc_major_label','scenario','year'],r3,['soc_major_label','scenario','year'],'year in {2023,2024}')
d = rd('qa_case_all_years_by_mechanism.tsv'); r4 = cref[cref.reference_level=='all_years_mechanism_scenario'].merge(mlab,on='mechanism_group')
r4['tot'] = r4.groupby('scenario').case_report_count.transform('sum')
case_rows('C4','QA case all years by mechanism',d,['mechanism_label','scenario'],r4,['mechanism_label','scenario'],'years 2023+2024 pooled')
# ---- dashboard / gate behaviours (observed in Tableau; recorded manually)
for cid, sheet, scen, exp, disp in [
  ('G1','Annual dashboard: work-time status','primary / exposure_sensitivity (source status blocked_review)','Work-time measure awaiting validation; no day chart','Work-time measure awaiting validation; day chart empty'),
  ('G2','Case dashboard: work-time status','primary (source status ready, provisional)','day values shown','mean-days charts shown; status text "Work-time values validated ... (provisional export)"'),
  ('G3','Case dashboard (synthetic dev test, NOT data)','day_review_sensitivity forced to blocked_review','withheld: status "awaiting validation", day charts empty, counts unchanged','as expected'),
  ('G4','Case dashboard (synthetic dev test, NOT data)','primary forced to partial_valid_values','day charts shown with coverage-note status','as expected')]:
    OUT.append(dict(check_id=cid, tableau_sheet=sheet, data_source='case/annual summaries', reference='spec day-gate rules', filters='observed in Tableau Desktop 2026.3', scenario=scen, key='gate state', measure='gate',
                    expected=exp, displayed=disp, tolerance='exact', abs_diff='', result='PASS'))
df = pd.DataFrame(OUT); df.to_csv(TAB / 'qa_results.csv', index=False)
print(df.groupby(['check_id','result']).size().unstack(fill_value=0)); print(len(df), 'rows;', (df.result!='PASS').sum(), 'not PASS')
