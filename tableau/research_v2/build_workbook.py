"""Generate the SafeShift research v2 Tableau workbook (.twb) and package it as .twbx.

Four separate CSV data sources are used and are never joined or blended:
  annual_size_summary.csv, annual_coverage.csv, case_pattern_summary.csv, case_coverage.csv

Usage:
  python build_workbook.py --annual-dir D --case-dir D --out-dir OUT [--case-label PROVISIONAL]
Creates OUT/SafeShift_research_v2.twb, OUT/Data/*.csv and OUT/SafeShift_research_v2.twbx.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

VERSION = "18.1"
Q = {"'": "&apos;", '"': "&quot;"}


def uid(seed: str) -> str:
    import uuid
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "safeshift-research-v2/" + seed)).upper() + "}"


def a(s: str) -> str:
    """Escape a string for use inside a single-quoted XML attribute."""
    return escape(s, Q)


# ----------------------------------------------------------------------------------------------
# Data sources
# ----------------------------------------------------------------------------------------------
class DS:
    def __init__(self, key: str, caption: str, filename: str, cols: list, calcs: list):
        self.key = key
        self.caption = caption
        self.filename = filename
        self.name = "federated." + {"A": "1rxrgdq1t0yllh102evw9053jy3g", "B": "1rxrgdq1t0yllh102evw9053jy3h",
                                    "C": "1rxrgdq1t0yllh102evw9053jy3i", "D": "1rxrgdq1t0yllh102evw9053jy3j"}[key]
        self.conn = "textscan." + {"A": "0mf09qf0h323l6181ycsk0mqdigx", "B": "0mf09qf0h323l6181ycsk0mqdigy",
                                   "C": "0mf09qf0h323l6181ycsk0mqdigz", "D": "0mf09qf0h323l6181ycsk0mqdig0"}[key]
        self.cols = cols      # (name, datatype, role, type)
        self.calcs = calcs    # dicts: id, caption, formula, datatype, role, type, fmt
        self.calc_by_id = {c["id"]: c for c in calcs}

    def ref(self, inst: str) -> str:
        return f"[{self.name}].[{inst}]"

    def calc_xml(self, c: dict) -> str:
        fmt = f" default-format='{a(c['fmt'])}'" if c.get("fmt") else ""
        return (f"<column caption='{a(c['caption'])}' datatype='{c['datatype']}'{fmt} "
                f"name='[{c['id']}]' role='{c['role']}' type='{c['type']}'>"
                f"<calculation class='tableau' formula='{a(c['formula'])}' /></column>")

    def datasource_xml(self, directory: str = "Data") -> str:
        import hashlib
        oid = f"{self.filename}_" + hashlib.md5(self.filename.encode()).hexdigest().upper()
        rt = {"integer": 20, "real": 5, "string": 129}
        agg = {"integer": "Sum", "real": "Sum", "string": "Count"}
        rel_cols = "".join(
            f"<column datatype='{dt}' name='{n}' ordinal='{i}' />" for i, (n, dt, _r, _t) in enumerate(self.cols)
        )
        relation = (
            f"<relation connection='{self.conn}' name='{a(self.filename)}' table='[{a(self.filename.replace('.', '#'))}]' type='table'>"
            f"<columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{rel_cols}</columns></relation>"
        )
        meta = (
            f"<metadata-record class='capability'><remote-name /><remote-type>0</remote-type>"
            f"<parent-name>[{a(self.filename)}]</parent-name><remote-alias /><aggregation>Count</aggregation>"
            "<contains-null>true</contains-null><attributes>"
            "<attribute datatype='string' name='character-set'>&quot;UTF-8&quot;</attribute>"
            "<attribute datatype='string' name='collation'>&quot;en_US&quot;</attribute>"
            "<attribute datatype='string' name='field-delimiter'>&quot;,&quot;</attribute>"
            "<attribute datatype='string' name='header-row'>&quot;true&quot;</attribute>"
            "<attribute datatype='string' name='locale'>&quot;en_US&quot;</attribute>"
            "<attribute datatype='string' name='single-char'>&quot;&quot;</attribute></attributes></metadata-record>"
        )
        for i, (n, dt, _r, _t) in enumerate(self.cols):
            extra = "<scale>1</scale><width>1073741823</width>" if dt == "string" else ""
            coll = "<collation flag='0' name='LEN_RUS' />" if dt == "string" else ""
            meta += (
                f"<metadata-record class='column'><remote-name>{n}</remote-name><remote-type>{rt[dt]}</remote-type>"
                f"<local-name>[{n}]</local-name><parent-name>[{a(self.filename)}]</parent-name><remote-alias>{n}</remote-alias>"
                f"<ordinal>{i}</ordinal><local-type>{dt}</local-type><aggregation>{agg[dt]}</aggregation>{extra}"
                f"<contains-null>true</contains-null>{coll}<object-id>[{oid}]</object-id></metadata-record>"
            )
        col_defs = (f"<column caption='{a(self.filename)}' datatype='table' "
                    f"name='[__tableau_internal_object_id__].[{oid}]' role='measure' type='quantitative' />")
        col_defs += "".join(
            f"<column datatype='{dt}' name='[{n}]' role='{r}' type='{t}' />" for (n, dt, r, t) in sorted(self.cols)
        )
        calcs = "".join(self.calc_xml(c) for c in self.calcs)
        return (
            f"<datasource caption='{a(self.caption)}' inline='true' name='{self.name}' version='{VERSION}'>"
            f"<connection class='federated'><named-connections>"
            f"<named-connection caption='{a(self.caption)}' name='{self.conn}'>"
            f"<connection class='textscan' directory='{a(directory)}' filename='{a(self.filename)}' password='' server='' />"
            f"</named-connection></named-connections>{relation}<metadata-records>{meta}</metadata-records>"
            f"</connection><aliases enabled='yes' />{col_defs}{calcs}"
            "<layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />"
            "<semantic-values><semantic-value key='[Country].[Name]' value='&quot;United States&quot;' /></semantic-values>"
            f"<object-graph><objects><object caption='{a(self.filename)}' id='{oid}'><properties context=''>"
            f"{relation}</properties></object></objects></object-graph></datasource>"
        )


def calc(cid, caption, formula, datatype, role="measure", typ="quantitative", fmt=None):
    return dict(id=cid, caption=caption, formula=formula, datatype=datatype, role=role, type=typ, fmt=fmt)


P_ANN = "[Parameters].[Parameter 1]"
P_CASE = "[Parameters].[Parameter 2]"

SIZE_CASE = ("CASE [size_group] WHEN 'lt_50' THEN 'Under 50' WHEN '50_249' THEN '50-249' "
             "WHEN '250_999' THEN '250-999' WHEN '1000_plus' THEN '1,000 or more' END")
GATE_ANN = "SUM(IIF([dafw_days_status] = 'blocked_review' OR [djtr_days_status] = 'blocked_review', 1, 0)) > 0"
GATE_ANN_PARTIAL = "SUM(IIF([dafw_days_status] = 'partial_valid_values' OR [djtr_days_status] = 'partial_valid_values', 1, 0)) > 0"
GATE_CASE = GATE_ANN

ANNUAL = DS(
    "A", "annual_size_summary", "annual_size_summary.csv",
    [("year", "integer", "dimension", "ordinal"), ("size_group", "string", "dimension", "nominal"),
     ("scenario", "string", "dimension", "nominal"),
     ("establishment_year_count", "integer", "measure", "quantitative"),
     ("employee_count_sum", "real", "measure", "quantitative"), ("hours_sum", "real", "measure", "quantitative"),
     ("dafw_case_count", "real", "measure", "quantitative"), ("djtr_case_count", "real", "measure", "quantitative"),
     ("dart_case_count", "real", "measure", "quantitative"),
     ("dafw_days_eligible_establishment_years", "integer", "measure", "quantitative"),
     ("djtr_days_eligible_establishment_years", "integer", "measure", "quantitative"),
     ("dafw_days_cohort_dart_count", "real", "measure", "quantitative"),
     ("djtr_days_cohort_dart_count", "real", "measure", "quantitative"),
     ("size_group_order", "integer", "dimension", "ordinal"), ("dart_rate", "real", "measure", "quantitative"),
     ("dafw_days_sum", "real", "measure", "quantitative"), ("djtr_days_sum", "real", "measure", "quantitative"),
     ("dafw_days_status", "string", "dimension", "nominal"), ("djtr_days_status", "string", "dimension", "nominal")],
    [
        calc("Calculation_1100000000000001", "Annual scenario is selected", f"[scenario] = {P_ANN}", "boolean", "dimension", "nominal"),
        calc("Calculation_1100000000000002", "Establishment size (employees)", SIZE_CASE, "string", "dimension", "nominal"),
        calc("Calculation_1100000000000003", "Reported DART cases", "SUM([dart_case_count])", "integer", fmt="n#,##0"),
        calc("Calculation_1100000000000004", "DART cases per 100 FTE",
             "IF SUM([hours_sum]) > 0 THEN 200000 * SUM([dart_case_count]) / SUM([hours_sum]) END", "real", fmt="n#,##0.000"),
        calc("Calculation_1100000000000005", "Establishment-years", "SUM([establishment_year_count])", "integer", fmt="n#,##0"),
        calc("Calculation_1100000000000006", "Reported hours worked", "SUM([hours_sum])", "real", fmt="n#,##0"),
        calc("Calculation_1100000000000007", "Work-time measure status",
             f"IF {GATE_ANN} THEN 'Work-time measure awaiting validation' "
             f"ELSEIF {GATE_ANN_PARTIAL} THEN 'Work-time measure shown with coverage note: valid values only' "
             "ELSE 'Work-time measure validated for this scenario' END", "string", "measure", "nominal"),
        calc("Calculation_1100000000000008", "Reported days away (gated)",
             f"IF {GATE_ANN} THEN NULL ELSE SUM([dafw_days_sum]) END", "real", fmt="n#,##0"),
        calc("Calculation_1100000000000009", "Reported restricted/transfer days (gated)",
             f"IF {GATE_ANN} THEN NULL ELSE SUM([djtr_days_sum]) END", "real", fmt="n#,##0"),
        calc("Calculation_1100000000000010", "QA rate x 1e9 (integer)",
             "ROUND(1000000000 * [Calculation_1100000000000004], 0)", "real", fmt="n#,##0"),
    ],
)
ANNUAL_COV = DS(
    "B", "annual_coverage", "annual_coverage.csv",
    [("year", "integer", "dimension", "ordinal"), ("scenario", "string", "dimension", "nominal"),
     ("establishment_years", "integer", "measure", "quantitative"), ("contributing_hours", "real", "measure", "quantitative"),
     ("dart_missing", "integer", "measure", "quantitative"), ("hours_missing", "integer", "measure", "quantitative"),
     ("days_away_missing", "integer", "measure", "quantitative"), ("dafw_days_available", "integer", "measure", "quantitative"),
     ("restricted_days_missing", "integer", "measure", "quantitative"), ("djtr_days_available", "integer", "measure", "quantitative"),
     ("input_records", "integer", "measure", "quantitative"), ("primary_records", "integer", "measure", "quantitative"),
     ("excluded_naics", "integer", "measure", "quantitative"), ("excluded_core_fields", "integer", "measure", "quantitative"),
     ("excluded_duplicate_key", "integer", "measure", "quantitative"), ("structurally_excluded", "integer", "measure", "quantitative"),
     ("sensitivity_records", "integer", "measure", "quantitative"), ("exposure_excluded", "integer", "measure", "quantitative")],
    [
        calc("Calculation_1200000000000001", "Included of input records",
             "STR(SUM([establishment_years])) + ' of ' + STR(SUM([input_records]))", "string", "measure", "nominal"),
        calc("Calculation_1200000000000002", "Scenario label",
             "IF [scenario] = 'primary' THEN 'Primary' ELSE 'Exposure sensitivity' END", "string", "dimension", "nominal"),
    ],
)
CASE = DS(
    "C", "case_pattern_summary", "case_pattern_summary.csv",
    [("year", "integer", "dimension", "ordinal"), ("mechanism_group", "string", "dimension", "nominal"),
     ("mechanism_label", "string", "dimension", "nominal"), ("mechanism_order", "integer", "dimension", "ordinal"),
     ("soc_major_group", "string", "dimension", "nominal"), ("soc_major_label", "string", "dimension", "nominal"),
     ("soc_major_order", "integer", "dimension", "ordinal"), ("scenario", "string", "dimension", "nominal"),
     ("case_report_count", "integer", "measure", "quantitative"),
     ("outcome_death_count", "integer", "measure", "quantitative"), ("outcome_dafw_count", "integer", "measure", "quantitative"),
     ("outcome_djtr_count", "integer", "measure", "quantitative"), ("outcome_other_count", "integer", "measure", "quantitative"),
     ("outcome_unknown_count", "integer", "measure", "quantitative"),
     ("dafw_days_sum", "integer", "measure", "quantitative"), ("djtr_days_sum", "integer", "measure", "quantitative"),
     ("dafw_days_known_report_count", "integer", "measure", "quantitative"),
     ("djtr_days_known_report_count", "integer", "measure", "quantitative"),
     ("dafw_days_invalid_or_missing_count", "integer", "measure", "quantitative"),
     ("djtr_days_invalid_or_missing_count", "integer", "measure", "quantitative"),
     ("dafw_days_status", "string", "dimension", "nominal"), ("djtr_days_status", "string", "dimension", "nominal"),
     ("day_review_flag_report_count", "integer", "measure", "quantitative")],
    [
        calc("Calculation_1300000000000001", "Case scenario is selected", f"[scenario] = {P_CASE}", "boolean", "dimension", "nominal"),
        calc("Calculation_1300000000000002", "Case reports", "SUM([case_report_count])", "integer", fmt="n#,##0"),
        calc("Calculation_1300000000000003", "Percent of reports",
             "SUM([case_report_count]) / MIN({ EXCLUDE [mechanism_label] : SUM([case_report_count]) })", "real", fmt="p0.0%"),
        calc("Calculation_1300000000000004", "Mean days away per report (gated)",
             f"IF {GATE_CASE} THEN NULL ELSEIF SUM([dafw_days_known_report_count]) > 0 "
             "THEN SUM([dafw_days_sum]) / SUM([dafw_days_known_report_count]) END", "real", fmt="n#,##0.0"),
        calc("Calculation_1300000000000005", "Mean restricted/transfer days per report (gated)",
             f"IF {GATE_CASE} THEN NULL ELSEIF SUM([djtr_days_known_report_count]) > 0 "
             "THEN SUM([djtr_days_sum]) / SUM([djtr_days_known_report_count]) END", "real", fmt="n#,##0.0"),
        calc("Calculation_1300000000000006", "Work-time measure status",
             f"IF {GATE_CASE} THEN 'Work-time measure awaiting validation' "
             f"ELSEIF {GATE_ANN_PARTIAL} THEN 'Work-time measure shown with coverage note: valid values only' "
             "ELSE 'Work-time values validated for this scenario (provisional export)' END", "string", "measure", "nominal"),
        calc("Calculation_1300000000000007", "Days-away numerator", "SUM([dafw_days_sum])", "integer", fmt="n#,##0"),
        calc("Calculation_1300000000000008", "Days-away denominator (reports with valid value)",
             "SUM([dafw_days_known_report_count])", "integer", fmt="n#,##0"),
        calc("Calculation_1300000000000010", "QA mean days away x 1e9 (integer)",
             "ROUND(1000000000 * [Calculation_1300000000000004], 0)", "real", fmt="n#,##0"),
        calc("Calculation_1300000000000011", "QA mean restricted days x 1e9 (integer)",
             "ROUND(1000000000 * [Calculation_1300000000000005], 0)", "real", fmt="n#,##0"),
        calc("Calculation_1300000000000012", "QA percent of reports x 1e9 (integer)",
             "ROUND(1000000000 * [Calculation_1300000000000003], 0)", "real", fmt="n#,##0"),
        calc("Calculation_1300000000000013", "Restricted days numerator", "SUM([djtr_days_sum])", "integer", fmt="n#,##0"),
        calc("Calculation_1300000000000014", "Restricted days denominator (reports with valid value)",
             "SUM([djtr_days_known_report_count])", "integer", fmt="n#,##0"),
    ],
)
CASE_COV = DS(
    "D", "case_coverage", "case_coverage.csv",
    [("year", "integer", "dimension", "ordinal"), ("scenario", "string", "dimension", "nominal"),
     ("input_rows_all_industries", "integer", "measure", "quantitative"),
     ("warehouse_rows_naics_4931", "integer", "measure", "quantitative"),
     ("excluded_date_missing_or_invalid", "integer", "measure", "quantitative"),
     ("excluded_incident_year_mismatch", "integer", "measure", "quantitative"),
     ("excluded_day_review_flag", "integer", "measure", "quantitative"),
     ("included_report_count", "integer", "measure", "quantitative"),
     ("missing_event_code_reports", "integer", "measure", "quantitative"),
     ("other_reported_mechanism_reports", "integer", "measure", "quantitative"),
     ("unknown_occupation_reports", "integer", "measure", "quantitative"),
     ("dafw_days_known_reports", "integer", "measure", "quantitative"),
     ("djtr_days_known_reports", "integer", "measure", "quantitative"),
     ("outcome_unknown_reports", "integer", "measure", "quantitative"),
     ("decode_replacement_reports_retained", "integer", "measure", "quantitative")],
    [
        calc("Calculation_1400000000000001", "Included of warehouse reports",
             "STR(SUM([included_report_count])) + ' of ' + STR(SUM([warehouse_rows_naics_4931]))", "string", "measure", "nominal"),
        calc("Calculation_1400000000000002", "Unknown occupation / missing event code",
             "STR(SUM([unknown_occupation_reports])) + ' unknown occupation; ' + STR(SUM([missing_event_code_reports])) + ' missing event code'",
             "string", "measure", "nominal"),
    ],
)
SOURCES = [ANNUAL, ANNUAL_COV, CASE, CASE_COV]

PARAMS_XML = (
    f"<datasource hasconnection='false' inline='true' name='Parameters' version='{VERSION}'><aliases enabled='yes' />"
    "<column caption='Annual scenario' datatype='string' name='[Parameter 1]' param-domain-type='list' role='measure' type='nominal' value='&quot;primary&quot;'>"
    "<calculation class='tableau' formula='&quot;primary&quot;' /><members>"
    "<member alias='Primary (all valid establishment-years)' value='&quot;primary&quot;' />"
    "<member alias='Exposure sensitivity (employees &gt; 0, hours 100-8,784 per employee)' value='&quot;exposure_sensitivity&quot;' />"
    "</members></column>"
    "<column caption='Case scenario' datatype='string' name='[Parameter 2]' param-domain-type='list' role='measure' type='nominal' value='&quot;primary&quot;'>"
    "<calculation class='tableau' formula='&quot;primary&quot;' /><members>"
    "<member alias='Primary (all valid-date reports)' value='&quot;primary&quot;' />"
    "<member alias='Day-review sensitivity (excludes reports with &gt;180 days)' value='&quot;day_review_sensitivity&quot;' />"
    "</members></column></datasource>"
)

SIZE_ORDER = ["Under 50", "50-249", "250-999", "1,000 or more"]
SIZE_COLORS = ["#8ec1e6", "#4a90c2", "#2468a2", "#0b3c6e"]
MECH_ORDER = ["Transportation incidents", "Falls, slips, trips", "Harmful exposure", "Contact with objects/equipment",
              "Overexertion / bodily reaction", "Other reported mechanism", "Unknown / missing mechanism"]
MECH_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#9a9a9a", "#444444"]
SCEN_COLORS = ["#2468a2", "#d55e00"]


def palette(field: str, values: list, colors: list) -> str:
    maps = "".join(f"<map to='{c}'><bucket>&quot;{a(v)}&quot;</bucket></map>" for v, c in zip(values, colors))
    return f"<style-rule element='mark'><encoding attr='color' field='{field}' type='palette'>{maps}</encoding></style-rule>"


# ----------------------------------------------------------------------------------------------
# Worksheets
# ----------------------------------------------------------------------------------------------
def col_inst(col, deriv, name, typ):
    return f"<column-instance column='[{col}]' derivation='{deriv}' name='[{name}]' pivot='key' type='{typ}' />"


def raw_col(ds: DS, name: str) -> str:
    n, dt, r, t = next(c for c in ds.cols if c[0] == name)
    return f"<column datatype='{dt}' name='[{n}]' role='{r}' type='{t}' />"


def worksheet(name, ds: DS, *, title, deps, filters, rows, cols, mark, encodings="", styles="", sorts="",
              uses_param=None, fmt_title=None, extra_pane="", tooltip=""):
    """deps: list of xml strings for datasource-dependencies; filters: list of filter xml; slices column refs."""
    params = f"<datasource hasconnection='false' name='Parameters' />" if uses_param else ""
    param_dep = ""
    if uses_param:
        pcols = {P_ANN: ("Parameter 1", "Annual scenario"), P_CASE: ("Parameter 2", "Case scenario")}[uses_param]
        param_dep = (f"<datasource-dependencies datasource='Parameters'><column caption='{pcols[1]}' datatype='string' "
                     f"name='[{pcols[0]}]' param-domain-type='list' role='measure' type='nominal' value='&quot;primary&quot;'>"
                     "<calculation class='tableau' formula='&quot;primary&quot;' /></column></datasource-dependencies>")
    slices = "".join(f"<column>{f[1]}</column>" for f in filters)
    fx = "".join(f[0] for f in filters)
    layout = (f"<layout-options><title><formatted-text><run bold='true' fontsize='11'>{a(title)}</run></formatted-text></title></layout-options>")
    return (
        f"<worksheet name='{a(name)}'>{layout}<table><view><datasources>"
        f"<datasource caption='{a(ds.caption)}' name='{ds.name}' />{params}</datasources>"
        f"<datasource-dependencies datasource='{ds.name}'>{''.join(deps)}</datasource-dependencies>{param_dep}"
        f"{fx}{sorts}{'<slices>' + slices + '</slices>' if slices else ''}<aggregation value='true' /></view>"
        f"<style>{styles}</style>"
        f"<panes><pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view>"
        f"<mark class='{mark}' />{'<encodings>' + encodings + '</encodings>' if encodings else ''}{tooltip}{extra_pane}</pane></panes>"
        f"<rows>{rows}</rows><cols>{cols}</cols></table><simple-id uuid='{uid(name)}' /></worksheet>"
    )


def scen_filter(ds: DS, cid: str):
    ref = ds.ref(cid)
    f = (f"<filter class='categorical' column='{ref}'><groupfilter function='member' level='[{cid}]' member='true' "
         "user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' /></filter>")
    return f, ref


def all_filter(ds: DS, col: str, inst: str, members=("2023", "2024")):
    ref = ds.ref(inst)
    mem = "".join(f"<groupfilter function='member' level='[{inst}]' member='{m}' />" for m in members)
    f = (f"<filter class='categorical' column='{ref}'><groupfilter function='union' user:ui-domain='database' "
         f"user:ui-enumeration='inclusive' user:ui-marker='enumerate'>{mem}</groupfilter></filter>")
    return f, ref


def tip(lines):
    """lines: list of (label, field-ref or None) ; builds a custom tooltip."""
    runs = ""
    for label, fld in lines:
        runs += f"<run>{a(label)}</run>"
        if fld:
            runs += f"<run bold='true'>&lt;[{a(fld)}]&gt;</run>"
        runs += "<run>&#10;</run>"
    return f"<customized-tooltip><formatted-text>{runs}</formatted-text></customized-tooltip>"


def build_sheets(case_label: str) -> dict:
    A, B, C, D = ANNUAL, ANNUAL_COV, CASE, CASE_COV
    s = {}
    cs, cl, cc, cr, ce, ch = (f"Calculation_11000000000000{n}" for n in ("01", "02", "03", "04", "05", "06"))
    cstat, cdaf, cdjt = "Calculation_1100000000000007", "Calculation_1100000000000008", "Calculation_1100000000000009"

    # ---- Annual: cases by size
    ref_year = A.ref("none:year:ok")
    ref_size = A.ref(f"none:{cl}:nk")
    ref_cases = A.ref(f"usr:{cc}:qk")
    ref_rate = A.ref(f"usr:{cr}:qk")
    ref_est = A.ref(f"usr:{ce}:qk")
    ref_hrs = A.ref(f"usr:{ch}:qk")
    ref_scen = A.ref("none:scenario:nk")
    base_deps = [
        raw_col(A, "year"), raw_col(A, "scenario"), raw_col(A, "size_group"), raw_col(A, "size_group_order"),
        raw_col(A, "dart_case_count"), raw_col(A, "hours_sum"), raw_col(A, "establishment_year_count"),
        A.calc_xml(A.calc_by_id[cs]), A.calc_xml(A.calc_by_id[cl]), A.calc_xml(A.calc_by_id[cc]),
        A.calc_xml(A.calc_by_id[cr]), A.calc_xml(A.calc_by_id[ce]), A.calc_xml(A.calc_by_id[ch]),
        col_inst("year", "None", "none:year:ok", "ordinal"),
        col_inst("scenario", "None", "none:scenario:nk", "nominal"),
        col_inst(cl, "None", f"none:{cl}:nk", "nominal"),
        col_inst(cc, "User", f"usr:{cc}:qk", "quantitative"), col_inst(cr, "User", f"usr:{cr}:qk", "quantitative"),
        col_inst(ce, "User", f"usr:{ce}:qk", "quantitative"), col_inst(ch, "User", f"usr:{ch}:qk", "quantitative"),
    ]
    pal = palette(ref_size, SIZE_ORDER, SIZE_COLORS)
    size_sort = (f"<sort class='manual' column='{ref_size}' direction='ASC'><dictionary>"
                 + "".join(f"<bucket>&quot;{a(v)}&quot;</bucket>" for v in SIZE_ORDER) + "</dictionary></sort>")
    s["Annual cases by size"] = worksheet(
        "Annual cases by size", A, title="Reported DART cases by establishment size",
        deps=base_deps, filters=[scen_filter(A, cs)], rows=ref_cases, cols=ref_year, mark="Bar",
        encodings=f"<color column='{ref_size}' /><tooltip column='{ref_est}' /><tooltip column='{ref_hrs}' />",
        styles=pal, sorts=size_sort, uses_param=P_ANN,
        tooltip=tip([("Reported DART cases (numerator): ", f"{A.name}].[usr:{cc}:qk"),
                     ("Establishment-years: ", f"{A.name}].[usr:{ce}:qk"), ("Hours worked: ", f"{A.name}].[usr:{ch}:qk"),
                     ("Scenario: ", "Parameters].[Parameter 1")]),
    )
    s["Annual rates by size"] = worksheet(
        "Annual rates by size", A, title="DART cases per 100 FTE (200,000 hours), pooled from reported cases and hours",
        deps=base_deps, filters=[scen_filter(A, cs)], rows=ref_rate, cols=ref_year, mark="Line",
        encodings=f"<color column='{ref_size}' /><tooltip column='{ref_cases}' /><tooltip column='{ref_hrs}' />",
        styles=pal, sorts=size_sort, uses_param=P_ANN,
        tooltip=tip([("DART cases per 100 FTE: ", f"{A.name}].[usr:{cr}:qk"),
                     ("Cases (numerator): ", f"{A.name}].[usr:{cc}:qk"), ("Hours (denominator): ", f"{A.name}].[usr:{ch}:qk"),
                     ("Scenario: ", "Parameters].[Parameter 1")]),
    )
    # ---- Denominators crosstab (establishment-years)
    s["Annual denominators"] = worksheet(
        "Annual denominators", A, title="Establishment-years by size (reporting records, not distinct establishments)",
        deps=base_deps, filters=[scen_filter(A, cs)], rows=ref_size, cols=ref_year, mark="Text",
        encodings=f"<text column='{ref_est}' />", sorts=size_sort, uses_param=P_ANN,
    )
    # ---- Day gate
    s["Annual days gate"] = worksheet(
        "Annual days gate", A, title="Days away / restricted days",
        deps=base_deps + [A.calc_xml(A.calc_by_id[cstat]), col_inst(cstat, "User", f"usr:{cstat}:nk", "nominal")],
        filters=[scen_filter(A, cs)], rows="", cols="", mark="Text",
        encodings=f"<text column='{A.ref(f'usr:{cstat}:nk')}' />", uses_param=P_ANN,
    )
    s["Annual days chart (gated)"] = worksheet(
        "Annual days chart (gated)", A, title="Reported days away from work (shown only when validated)",
        deps=base_deps + [A.calc_xml(A.calc_by_id[cdaf]), col_inst(cdaf, "User", f"usr:{cdaf}:qk", "quantitative")],
        filters=[scen_filter(A, cs)], rows=A.ref(f"usr:{cdaf}:qk"), cols=ref_year, mark="Bar",
        encodings=f"<color column='{ref_size}' />", styles=pal, sorts=size_sort, uses_param=P_ANN,
    )
    # ---- Annual coverage
    rb_year = B.ref("none:year:ok")
    rb_scen = B.ref("none:Calculation_1200000000000002:nk")
    rb_txt = B.ref("usr:Calculation_1200000000000001:nk")
    s["Annual coverage"] = worksheet(
        "Annual coverage", B, title="Annual coverage: establishment-years included of input records",
        deps=[raw_col(B, "year"), raw_col(B, "scenario"), raw_col(B, "establishment_years"), raw_col(B, "input_records"),
              B.calc_xml(B.calc_by_id["Calculation_1200000000000001"]), B.calc_xml(B.calc_by_id["Calculation_1200000000000002"]),
              col_inst("year", "None", "none:year:ok", "ordinal"),
              col_inst("Calculation_1200000000000002", "None", "none:Calculation_1200000000000002:nk", "nominal"),
              col_inst("Calculation_1200000000000001", "User", "usr:Calculation_1200000000000001:nk", "nominal")],
        filters=[], rows=rb_year, cols=rb_scen, mark="Text", encodings=f"<text column='{rb_txt}' />",
    )

    # ---- Case sheets
    ys = C.ref("none:year:ok")
    scn = "Calculation_1300000000000001"
    ccount, cpct, cmd, cmr = ("Calculation_1300000000000002", "Calculation_1300000000000003",
                              "Calculation_1300000000000004", "Calculation_1300000000000005")
    cstat2, cnum, cden = "Calculation_1300000000000006", "Calculation_1300000000000007", "Calculation_1300000000000008"
    mech = C.ref("none:mechanism_label:nk")
    soc = C.ref("none:soc_major_label:nk")
    mech_sort = (f"<sort class='computed' column='{mech}' direction='ASC' using='{C.ref('min:mechanism_order:qk')}' />")
    soc_sort = (f"<sort class='computed' column='{soc}' direction='DESC' using='{C.ref(f'usr:{ccount}:qk')}' />")
    cdeps = [raw_col(C, "year"), raw_col(C, "scenario"), raw_col(C, "mechanism_label"), raw_col(C, "mechanism_order"),
             raw_col(C, "soc_major_label"), raw_col(C, "case_report_count"),
             raw_col(C, "dafw_days_sum"), raw_col(C, "djtr_days_sum"),
             raw_col(C, "dafw_days_known_report_count"), raw_col(C, "djtr_days_known_report_count"),
             raw_col(C, "dafw_days_status"), raw_col(C, "djtr_days_status")]
    cdeps += [C.calc_xml(C.calc_by_id[k]) for k in (scn, ccount, cpct, cmd, cmr, cstat2, cnum, cden)]
    cdeps += [col_inst("year", "None", "none:year:ok", "ordinal"),
              col_inst("mechanism_label", "None", "none:mechanism_label:nk", "nominal"),
              col_inst("mechanism_order", "Min", "min:mechanism_order:qk", "quantitative"),
              col_inst("soc_major_label", "None", "none:soc_major_label:nk", "nominal"),
              col_inst(scn, "None", f"none:{scn}:nk", "nominal"), col_inst("scenario", "None", "none:scenario:nk", "nominal")]
    cdeps += [col_inst(k, "User", f"usr:{k}:qk", "quantitative") for k in (ccount, cpct, cmd, cmr, cnum, cden)]
    cdeps += [col_inst(cstat2, "User", f"usr:{cstat2}:nk", "nominal")]
    mpal = palette(mech, MECH_ORDER, MECH_COLORS)
    cfilters = [scen_filter(C, scn), all_filter(C, "year", "none:year:ok")]
    pct = C.ref(f"usr:{cpct}:qk")
    s["Case mechanism share"] = worksheet(
        "Case mechanism share", C, title=f"Percent of reports by incident mechanism ({case_label})",
        deps=cdeps, filters=cfilters, rows=mech, cols=pct, mark="Bar",
        encodings=(f"<color column='{mech}' /><text column='{pct}' /><tooltip column='{C.ref(f'usr:{ccount}:qk')}' />"
                   ""),
        styles=mpal, sorts=mech_sort, uses_param=P_CASE,
        tooltip=tip([("Mechanism: ", f"{C.name}].[none:mechanism_label:nk"), ("Percent of reports: ", f"{C.name}].[usr:{cpct}:qk"),
                     ("Reports (numerator): ", f"{C.name}].[usr:{ccount}:qk"),
                     ("Scenario: ", "Parameters].[Parameter 2")]),
    )
    s["Case occupation by mechanism"] = worksheet(
        "Case occupation by mechanism", C, title=f"Case reports by occupation (SOC major group) and mechanism ({case_label})",
        deps=cdeps, filters=cfilters, rows=soc, cols=C.ref(f"usr:{ccount}:qk"), mark="Bar",
        encodings=f"<color column='{mech}' />", styles=mpal, sorts=soc_sort, uses_param=P_CASE,
    )
    s["Case days by mechanism"] = worksheet(
        "Case days by mechanism", C, title=f"Mean reported days per report with a valid value ({case_label})",
        deps=cdeps, filters=cfilters, rows=mech, cols=f"({C.ref(f'usr:{cmd}:qk')} + {C.ref(f'usr:{cmr}:qk')})", mark="Bar",
        encodings=f"<color column='{mech}' /><tooltip column='{C.ref(f'usr:{cnum}:qk')}' /><tooltip column='{C.ref(f'usr:{cden}:qk')}' />",
        styles=mpal, sorts=mech_sort, uses_param=P_CASE,
        tooltip=tip([("Mechanism: ", f"{C.name}].[none:mechanism_label:nk"),
                     ("Mean days away per report: ", f"{C.name}].[usr:{cmd}:qk"),
                     ("Days away (numerator): ", f"{C.name}].[usr:{cnum}:qk"),
                     ("Reports with valid value (denominator): ", f"{C.name}].[usr:{cden}:qk")]),
    )
    s["Case days gate"] = worksheet(
        "Case days gate", C, title="Work-time measure status", deps=cdeps, filters=cfilters, rows="", cols="", mark="Text",
        encodings=f"<text column='{C.ref(f'usr:{cstat2}:nk')}' />", uses_param=P_CASE,
    )
    dd = D.ref("none:year:ok")
    s["Case coverage"] = worksheet(
        "Case coverage", D, title="Case coverage: included reports of warehouse (NAICS 4931) reports",
        deps=[raw_col(D, "year"), raw_col(D, "scenario"), raw_col(D, "included_report_count"),
              raw_col(D, "warehouse_rows_naics_4931"), raw_col(D, "unknown_occupation_reports"),
              raw_col(D, "missing_event_code_reports"),
              D.calc_xml(D.calc_by_id["Calculation_1400000000000001"]), D.calc_xml(D.calc_by_id["Calculation_1400000000000002"]),
              col_inst("year", "None", "none:year:ok", "ordinal"), col_inst("scenario", "None", "none:scenario:nk", "nominal"),
              col_inst("Calculation_1400000000000001", "User", "usr:Calculation_1400000000000001:nk", "nominal"),
              col_inst("Calculation_1400000000000002", "User", "usr:Calculation_1400000000000002:nk", "nominal")],
        filters=[], rows=f"({dd} / {D.ref('none:scenario:nk')})", cols="", mark="Text",
        encodings=(f"<text column='{D.ref('usr:Calculation_1400000000000001:nk')}' />"
                   f"<text column='{D.ref('usr:Calculation_1400000000000002:nk')}' />"),
    )

    # ---- QA-only sheets (both scenarios shown as a dimension; integer-scaled values give full precision; not on any dashboard)
    qr = "Calculation_1100000000000010"
    A_extra = [A.calc_xml(A.calc_by_id[qr]), col_inst(qr, "User", f"usr:{qr}:qk", "quantitative")]
    ann_meas = [ref_est, ref_hrs, ref_cases, ref_rate, A.ref(f"usr:{qr}:qk")]
    s["QA annual by year"] = worksheet(
        "QA annual by year", A, title="QA only: annual totals by year and scenario (rate x 1e9 shown as integer)",
        deps=base_deps + A_extra, filters=[], rows=f"({ref_year} / {ref_scen})", cols="(" + " + ".join(ann_meas) + ")", mark="Bar")
    s["QA annual by size"] = worksheet(
        "QA annual by size", A, title="QA only: annual totals by year, size and scenario (rate x 1e9 shown as integer)",
        deps=base_deps + A_extra, filters=[], rows=f"({ref_year} / {ref_size} / {ref_scen})",
        cols="(" + " + ".join(ann_meas) + ")", mark="Bar")
    qk = ("Calculation_1300000000000010", "Calculation_1300000000000011", "Calculation_1300000000000012",
          "Calculation_1300000000000013", "Calculation_1300000000000014")
    C_extra = [C.calc_xml(C.calc_by_id[k]) for k in qk] + [col_inst(k, "User", f"usr:{k}:qk", "quantitative") for k in qk]
    cm = [C.ref(f"usr:{k}:qk") for k in (ccount, cnum, cden, qk[3], qk[4], qk[0], qk[1])]
    cp = C.ref(f"usr:{qk[2]}:qk")
    scn_c = C.ref("none:scenario:nk")
    s["QA case by year"] = worksheet(
        "QA case by year", C, title="QA only: case totals by year and scenario", deps=cdeps + C_extra, filters=[],
        rows=f"({ys} / {scn_c})", cols="(" + " + ".join(cm) + ")", mark="Bar")
    s["QA case by mechanism"] = worksheet(
        "QA case by mechanism", C, title="QA only: case totals by year, mechanism and scenario", deps=cdeps + C_extra, filters=[],
        rows=f"({ys} / {mech} / {scn_c})", cols="(" + " + ".join(cm + [cp]) + ")", mark="Bar")
    s["QA case by occupation"] = worksheet(
        "QA case by occupation", C, title="QA only: case totals by year, occupation and scenario", deps=cdeps + C_extra, filters=[],
        rows=f"({ys} / {soc} / {scn_c})", cols="(" + " + ".join(cm) + ")", mark="Bar")
    s["QA case all years by mechanism"] = worksheet(
        "QA case all years by mechanism", C, title="QA only: case totals pooled over 2023-2024 by mechanism and scenario",
        deps=cdeps + C_extra, filters=[], rows=f"({mech} / {scn_c})", cols="(" + " + ".join(cm + [cp]) + ")", mark="Bar")
    return s


# ----------------------------------------------------------------------------------------------
# Dashboards
# ----------------------------------------------------------------------------------------------
class Z:
    n = 10

    @classmethod
    def nid(cls):
        cls.n += 1
        return cls.n


def zone_sheet(name, x, y, w, h, extra=""):
    return f"<zone h='{h}' id='{Z.nid()}' name='{a(name)}' w='{w}' x='{x}' y='{y}'{extra}></zone>"


def zone_text(runs, x, y, w, h):
    body = "".join(f"<run {attrs}>{a(t)}</run>" for t, attrs in runs)
    return f"<zone h='{h}' id='{Z.nid()}' type-v2='text' w='{w}' x='{x}' y='{y}'><formatted-text>{body}</formatted-text></zone>"


def zone_param(param, x, y, w, h):
    return f"<zone h='{h}' id='{Z.nid()}' param='{param}' type-v2='paramctrl' w='{w}' x='{x}' y='{y}' />"


def zone_legend(sheet, field, x, y, w, h):
    return (f"<zone h='{h}' id='{Z.nid()}' name='{a(sheet)}' param='{field}' type-v2='color' w='{w}' x='{x}' y='{y}' />")


def zone_filter(sheet, field, x, y, w, h):
    return (f"<zone h='{h}' id='{Z.nid()}' name='{a(sheet)}' param='{field}' type-v2='filter' w='{w}' x='{x}' y='{y}' />")


DASH_SHEETS: dict = {}


def dashboard(name, zones: list, sources: list, w=1400, h=1000):
    import re
    DASH_SHEETS[name] = list(dict.fromkeys(m.group(1) for z in zones for m in [re.match(r"<zone [^>]*?name='([^']+)'", z)] if m and 'type-v2' not in z.split('>')[0]))
    root = (f"<zone h='100000' id='4' type-v2='layout-basic' w='100000' x='0' y='0'>{''.join(zones)}</zone>")
    dss = "".join(f"<datasource caption='{a(d.caption)}' name='{d.name}' />" for d in sources)
    if any(d.key in ("A", "C") for d in sources):
        dss += "<datasource name='Parameters' />"
    return (f"<dashboard name='{a(name)}'><style />"
            f"<size maxheight='{h}' maxwidth='{w}' minheight='{h}' minwidth='{w}' sizing-mode='fixed' />"
            f"<datasources>{dss}</datasources><zones>{root}</zones>"
            f"<simple-id uuid='{uid('dash/' + name)}' /></dashboard>")


ANNUAL_TITLE = "Reported warehouse cases and rates by establishment size, 2016-2025"
CASE_TITLE = "Mechanisms and occupations in reported warehouse cases, 2023-2024"
METHODS_TITLE = "Methods, coverage and limitations"

ANN_NOTE = ("Descriptive and exploratory. Source: OSHA Injury Tracking Application (ITA) annual Form 300A summaries, "
            "warehousing and storage (NAICS 4931). Rate = 200,000 x DART cases / hours, pooled from sums (never averaged). "
            "Establishment size = annual average employees. Establishment-years are reporting records and are not distinct "
            "establishments. Differences by size describe reported data only; they do not show causes or which establishments are safer.")
CASE_NOTE = ("Descriptive and exploratory. Source: OSHA ITA Case Detail, warehousing and storage (NAICS 4931), 2023-2024 reported "
             "cases only. Occupation is the SOC 2018 major group from the reported code; unknown or uncodable occupations are "
             "kept as Unknown. Case data are a separate source from the annual establishment data and are not comparable to them. "
             "Mechanism groups are assigned from Event codes by a frozen year-specific map.")


def build_dashboards(case_label: str) -> str:
    Z.n = 10
    A, C = ANNUAL, CASE
    cl = "Calculation_1100000000000002"
    ann = [
        zone_text([(ANNUAL_TITLE, "bold='true' fontsize='20'")], 0, 0, 100000, 6000),
        zone_text([(ANN_NOTE, "fontsize='10'")], 0, 6000, 100000, 7000),
        zone_param(P_ANN, 0, 13000, 22000, 8000),
        zone_legend("Annual cases by size", A.ref(f"none:{cl}:nk"), 0, 21000, 22000, 14000),
        zone_text([("Scenario switch applies to every chart on this page. Primary is the default. "
                    "2025 primary hours include one extreme-hours record, so compare it with the exposure-sensitivity scenario.",
                    "fontsize='10'")], 0, 35000, 22000, 17000),
        zone_sheet("Annual cases by size", 22000, 13000, 39000, 40000),
        zone_sheet("Annual rates by size", 61000, 13000, 39000, 40000),
        zone_sheet("Annual denominators", 0, 53000, 61000, 30000),
        zone_sheet("Annual days gate", 61000, 53000, 39000, 14000),
        zone_text([("Days away and restricted days: the annual day totals are withheld until the work-time review is "
                    "complete. No day chart is shown while a scenario carries the blocked_review status.", "fontsize='10'")],
                  61000, 67000, 39000, 16000),
        zone_text([("Reported data, not a complete census of warehouse injuries. Rates use reported hours and are not adjusted "
                    "for job mix, shift, or other risk factors.", "fontsize='9'")], 0, 83000, 100000, 17000),
    ]
    mech = C.ref("none:mechanism_label:nk")
    cas = [
        zone_text([(CASE_TITLE, "bold='true' fontsize='20'")], 0, 0, 100000, 6000),
        zone_text([(f"{case_label.upper()}: ", "bold='true' fontsize='10'"), (CASE_NOTE, "fontsize='10'")], 0, 6000, 100000, 7000),
        zone_param(P_CASE, 0, 13000, 22000, 8000),
        zone_filter("Case mechanism share", C.ref("none:year:ok"), 0, 21000, 22000, 10000),
        zone_legend("Case occupation by mechanism", mech, 0, 31000, 22000, 22000),
        zone_sheet("Case mechanism share", 22000, 13000, 39000, 38000),
        zone_sheet("Case occupation by mechanism", 61000, 13000, 39000, 38000),
        zone_sheet("Case days by mechanism", 22000, 51000, 54000, 32000),
        zone_sheet("Case days gate", 76000, 51000, 24000, 10000),
        zone_text([("Mean days divide summed days by reports with a valid day value. Reports with outcome DAFW but zero days "
                    "are reported as is; see the QA note.", "fontsize='9'")], 76000, 61000, 24000, 22000),
        zone_text([("Counts are reports in the OSHA Case Detail files, not distinct workers. Reports are not weighted to "
                    "national totals, and the 2023 and 2024 files use different date and code conventions.", "fontsize='9'")],
                  0, 83000, 100000, 17000),
    ]
    meth = [
        zone_text([(METHODS_TITLE, "bold='true' fontsize='20'")], 0, 0, 100000, 6000),
        zone_text([("Annual: " + ANN_NOTE + "\n\nCases: " + CASE_NOTE + "\n\nScenarios. Annual primary = structurally valid "
                    "establishment-years. Exposure sensitivity = primary records with employees > 0 and hours between 100 and 8,784 per "
                    "employee. Case primary = reports with a valid date in the file year. Day-review sensitivity also excludes reports "
                    "with more than 180 days (a review flag, never a cap).", "fontsize='10'")], 0, 6000, 100000, 32000),
        zone_sheet("Annual coverage", 0, 38000, 50000, 62000),
        zone_sheet("Case coverage", 50000, 38000, 50000, 62000),
    ]
    return ("<dashboards>" + dashboard("Annual dashboard", ann, [ANNUAL]) + dashboard("Case dashboard", cas, [CASE])
            + dashboard("Methods and coverage", meth, [ANNUAL_COV, CASE_COV]) + "</dashboards>")


def build_twb(case_label: str, stage: str = 'all', only: list | None = None, directory: str = 'Data') -> str:
    sheets = build_sheets(case_label)
    order = ["Annual cases by size", "Annual rates by size", "Annual denominators", "Annual days gate",
             "Annual days chart (gated)", "Annual coverage", "Case mechanism share", "Case occupation by mechanism",
             "Case days by mechanism", "Case days gate", "Case coverage",
             "QA annual by year", "QA annual by size", "QA case by year", "QA case by mechanism", "QA case by occupation",
             "QA case all years by mechanism"]
    ds_xml = "".join(d.datasource_xml(directory) for d in SOURCES) + PARAMS_XML
    dash_xml = build_dashboards(case_label) if stage == 'all' else ""
    wnames = [k for k in order if (only is None or k in only)] if stage != 'ds' else []
    dnames = ["Annual dashboard", "Case dashboard", "Methods and coverage"] if stage == 'all' else []
    cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' /></strip></edge>"
             "<edge name='top'><strip size='2147483647'><card type='columns' /></strip><strip size='2147483647'><card type='rows' /></strip>"
             "<strip size='31'><card type='title' /></strip></edge></cards>")
    windows = "<windows source-height='30'>"
    windows += "".join(f"<window class='worksheet' name='{a(k)}'>{cards}<simple-id uuid='{uid('win/' + k)}' /></window>" for k in wnames)
    windows += "".join(
        f"<window class='dashboard' name='{a(k)}'><viewpoints>"
        + "".join(f"<viewpoint name='{a(v)}'><zoom type='entire-view' /></viewpoint>" for v in DASH_SHEETS.get(k, []))
        + f"</viewpoints><active id='-1' /><simple-id uuid='{uid('win/' + k)}' /></window>" for k in dnames)
    windows += "</windows>"
    return (
        "<?xml version='1.0' encoding='utf-8' ?>\n"
        f"<workbook original-version='{VERSION}' source-build='2026.3.0 (20263.26.0000.0000)' source-platform='mac' version='{VERSION}' "
        "xmlns:user='http://www.tableausoftware.com/xml/user'><document-format-change-manifest><AnimationOnByDefault /><MarkAnimation /><ObjectModelEncapsulateLegacy /><ObjectModelTableType /><SchemaViewerObjectModel /><SheetIdentifierTracking /><WindowsPersistSimpleIdentifiers /></document-format-change-manifest><preferences><preference name='ui.encoding.shelf.height' value='24' />"
        "<preference name='ui.shelf.height' value='26' /></preferences>"
        f"<datasources>{ds_xml}</datasources>"
        + (f"<worksheets>{''.join(sheets[k] for k in order if (only is None or k in only))}</worksheets>" if stage != 'ds' else "")
        + dash_xml + windows + "</workbook>\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annual-dir", type=Path, required=True)
    ap.add_argument("--case-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--case-label", default="provisional case export")
    ap.add_argument("--name", default="SafeShift_research_v2")
    ap.add_argument("--data-directory", default="Data")
    ap.add_argument("--stage", default="all", choices=["ds", "ws", "all"])
    ap.add_argument("--only", default="", help="comma-separated worksheet names (stage ws)")
    args = ap.parse_args()
    out = args.out_dir
    (out / "Data").mkdir(parents=True, exist_ok=True)
    for src in (args.annual_dir / "annual_size_summary.csv", args.annual_dir / "annual_coverage.csv",
                args.case_dir / "case_pattern_summary.csv", args.case_dir / "case_coverage.csv"):
        shutil.copyfile(src, out / "Data" / src.name)
    twb = out / f"{args.name}.twb"
    twb.write_text(build_twb(args.case_label, args.stage, [x for x in args.only.split(',') if x] or None, args.data_directory), encoding="utf-8")
    twbx = out / f"{args.name}.twbx"
    with zipfile.ZipFile(twbx, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(twb, twb.name)
        for f in sorted((out / "Data").iterdir()):
            z.write(f, f"Data/{f.name}")
    print("wrote", twb, twbx)


if __name__ == "__main__":
    main()
