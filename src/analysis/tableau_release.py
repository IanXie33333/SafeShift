"""Create a native Tableau workbook/package and explicit application QA references."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

USER = "http://www.tableausoftware.com/xml/user"
ET.register_namespace("user", USER)
SIZE_LABELS = {"lt_50": "Fewer than 50", "50_249": "50–249", "250_999": "250–999",
               "1000_plus": "1,000 or more"}
ANNUAL_REQUIRED = ["year", "size_group", "size_group_order", "scenario", "establishment_year_count",
                   "hours_sum", "dart_case_count", "dafw_days_sum", "djtr_days_sum",
                   "dafw_days_status", "djtr_days_status"]
CASE_REQUIRED = ["year", "scenario", "mechanism_group", "mechanism_label", "soc_major",
                 "soc_major_label", "case_report_count", "dafw_days_sum", "djtr_days_sum",
                 "outcome_dafw_count",
                 "dafw_days_known_report_count", "djtr_days_known_report_count",
                 "dafw_days_status", "djtr_days_status"]


def require(value, message):
    if not value:
        raise ValueError(message)


def node(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})
    if text is not None:
        element.text = str(text)
    return element


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def ref(source, instance):
    return f"[{source}].[{instance}]"


def parameter(parent, name, choices, default, aliases=None):
    field = node(parent, "column", caption=name, datatype="string", name=f"[{name}]",
                 param_domain_type="list", role="measure", type="nominal", value=quote(default))
    node(field, "calculation", **{"class": "tableau", "formula": quote(default)})
    members = node(field, "members")
    for value in choices:
        attrs = {"value": quote(value)}
        if aliases and value in aliases:
            attrs["alias"] = aliases[value]
        node(members, "member", **attrs)
    return field


def calculated(parent, name, formula, datatype="real", dimension=False):
    field = node(parent, "column", name=f"[{name}]", datatype=datatype,
                 role="dimension" if dimension else "measure",
                 type="nominal" if dimension else "quantitative")
    node(field, "calculation", **{"class": "tableau", "formula": formula})
    return field


def connection(parent, source, caption, filename, frame, formulas):
    datasource = node(parent, "datasource", caption=caption, inline="true", name=source, version="18.1")
    conn = node(datasource, "connection", **{"class": "federated"})
    named = node(node(conn, "named-connections"), "named-connection", name=source + ".leaf", caption=caption)
    node(named, "connection", **{"class": "textscan", "directory": "Data", "filename": filename,
                                 "password": "", "server": "", "workgroup-auth-mode": "as-is"})
    relation = node(conn, "relation", connection=source + ".leaf", name=filename,
                    table=f"[{filename[:-4]}#csv]", type="table")
    columns = node(relation, "columns", character_set="UTF-8", header="yes", locale="en_US",
                   separator=",", text_qualifier='"')
    types = {}
    dimensions = {"year", "size_group", "size_label", "size_group_order", "scenario",
                  "soc_major", "soc_major_label", "mechanism_group", "mechanism_label", "mechanism_order",
                  "dafw_days_status", "djtr_days_status"}
    for i, name in enumerate(frame):
        datatype = "string" if name in dimensions and name not in {
            "year", "size_group_order", "mechanism_order"} else (
                "integer" if pd.api.types.is_integer_dtype(frame[name]) else "real")
        if frame[name].dtype == object or pd.api.types.is_string_dtype(frame[name]):
            datatype = "string"
        node(columns, "column", datatype=datatype, name=name, ordinal=i)
        dimension = name in dimensions or datatype == "string"
        kind = "ordinal" if dimension and datatype != "string" else (
            "nominal" if dimension else "quantitative")
        types[name] = (datatype, dimension, kind)
    cols = node(conn, "cols")
    for name in frame:
        node(cols, "map", key=f"[{name}]", value=f"[{filename}].[{name}]")
    for name, (datatype, dimension, kind) in types.items():
        captions = {"case_report_count": "Case reports", "outcome_dafw_count": "Reports involving days away",
                    "dart_case_count": "Reported DART cases", "hours_sum": "Reported annual hours",
                    "establishment_year_count": "Reporting establishment-years",
                    "soc_major_label": "Occupational group", "mechanism_label": "Incident mechanism",
                    "occupation_short": "Occupation (SOC major)", "mechanism_short": "Mechanism",
                    "size_label": "Annual-average employment"}
        node(datasource, "column", name=f"[{name}]", datatype=datatype,
             role="dimension" if dimension else "measure", type=kind,
             caption=captions.get(name, name.replace("_", " ").capitalize()))
    for name, (formula, datatype, dimension) in formulas.items():
        calculated(datasource, name, formula, datatype, dimension)
        types[name] = (datatype, dimension, "nominal" if dimension else "quantitative")
    return datasource, types


def instance(types, field):
    _datatype, dimension, kind = types[field]
    derivation = "None" if dimension else ("User" if field in {
        "DART rate", "Report share", "Accepted DAFW days", "Accepted DJTR days", "Mean DAFW days"} else "Sum")
    suffix = "ok" if kind == "ordinal" else ("nk" if dimension else "qk")
    short = {"None": "none", "User": "usr", "Sum": "sum"}[derivation]
    return f"{short}:{field}:{suffix}", derivation, kind


def worksheet(parent, name, datasource, types, parameters, rows=None, cols=None, mark="Bar", color=None):
    source = datasource.attrib["name"]
    sheet = node(parent, "worksheet", name=name)
    title = node(node(node(sheet, "layout-options"), "title"), "formatted-text")
    node(title, "run", text=name, bold="true", fontname="Arial", fontsize="13")
    table = node(sheet, "table")
    view = node(table, "view")
    sources = node(view, "datasources")
    node(sources, "datasource", caption=datasource.attrib["caption"], name=source)
    node(sources, "datasource", caption="Parameters", name="Parameters")
    dependencies = node(view, "datasource-dependencies", datasource=source)
    for field in datasource.findall("column"):
        dependencies.append(copy.deepcopy(field))
    needed = {field for field in [rows, cols, color, "Visible rows"] if field}
    for field in sorted(needed):
        name_instance, derivation, kind = instance(types, field)
        node(dependencies, "column-instance", column=f"[{field}]", derivation=derivation,
             name=f"[{name_instance}]", pivot="key", type=kind)
    param_dependencies = node(view, "datasource-dependencies", datasource="Parameters")
    for field in parameters:
        param_dependencies.append(copy.deepcopy(field))
    visible = instance(types, "Visible rows")[0]
    filt = node(view, "filter", **{"class": "categorical", "column": ref(source, visible)})
    node(filt, "groupfilter", function="member", level=f"[{visible}]", member="true")
    node(view, "aggregation", value="true")
    node(table, "style")
    pane = node(node(table, "panes"), "pane")
    node(node(pane, "view"), "breakdown", value="auto")
    node(pane, "mark", **{"class": mark})
    if color:
        node(node(pane, "encodings"), "color", column=ref(source, instance(types, color)[0]))
    if mark == "Square" and color:
        # Keep the heatmap readable even without relying on its color scale.
        node(pane.find("encodings"), "text", column=ref(source, instance(types, color)[0]))
        style = node(pane, "style")
        rule = node(style, "style-rule", element="mark")
        node(rule, "format", attr="mark-labels-show", value="true")
    node(table, "rows", text=ref(source, instance(types, rows)[0]) if rows else "")
    node(table, "cols", text=ref(source, instance(types, cols)[0]) if cols else "")
    return sheet


def text_zone(parent, identifier, text, x, y, width, height, size=12, bold=False):
    zone = node(parent, "zone", id=identifier, type="text", x=x, y=y, w=width, h=height)
    formatted = node(zone, "formatted-text")
    node(formatted, "run", text=text, fontname="Arial", fontsize=size,
         fontcolor="#12263A", bold=str(bold).lower())
    return zone


def dashboard(parent, title, sheets, controls, note, legends=()):
    dash = node(parent, "dashboard", name=title)
    node(dash, "style")
    node(dash, "size", maxheight=950, maxwidth=1440, minheight=950, minwidth=1440)
    zones = node(dash, "zones")
    root = node(zones, "zone", id=1, type="layout-basic", x=0, y=0, w=100000, h=100000)
    text_zone(root, 2, title, 1500, 500, 97000, 6500, size=23, bold=True)
    control_width = int(97000 / max(1, len(controls)))
    for i, name in enumerate(controls):
        node(root, "zone", id=10 + i, type="paramctrl", mode="dropdown",
             param=f"[Parameters].[{name}]", x=1500 + i * control_width,
             y=7500, w=control_width - 700, h=6500)
    positions = [(1500, 15500), (43500, 15500), (1500, 55000), (43500, 55000)]
    for i, (sheet, (x, y)) in enumerate(zip(sheets, positions, strict=True)):
        zone = node(root, "zone", id=30 + i, name=sheet, x=x, y=y, w=40000, h=37500)
        style = node(zone, "zone-style")
        node(style, "format", attr="border-style", value="none")
        node(style, "format", attr="margin", value="8")
    for i, (sheet, column, y) in enumerate(legends):
        node(root, "zone", id=60 + i, type="color", name=sheet, param=column,
             x=85000, y=y, w=14000, h=30000)
    text_zone(root, 50, note, 1500, 94000, 97000, 5500, size=10)
    node(dash, "simple-id", uuid="{" + str(uuid.uuid5(uuid.NAMESPACE_URL, title)).upper() + "}")
    return dash


def workbook_xml(annual, cases):
    book = ET.Element("workbook", {"original-version": "18.1", "source-build": "2018.1.0",
                                  "source-platform": "mac", "version": "18.1", "xmlns:user": USER})
    preferences = node(book, "preferences")
    node(preferences, "preference", name="ui.encoding.shelf.height", value="24")
    datasources = node(book, "datasources")
    params = node(datasources, "datasource", name="Parameters", inline="true", version="18.1", hasconnection="false")
    parameter(params, "Annual scenario", ["primary", "exposure_sensitivity"], "primary",
              {"primary": "Primary reported data", "exposure_sensitivity": "Exposure sensitivity"})
    parameter(params, "Annual year", ["All years", "2023–2024",
                                      *[str(v) for v in sorted(annual.year.unique())]], "All years")
    parameter(params, "Annual size", ["All sizes", *SIZE_LABELS], "All sizes", SIZE_LABELS)
    parameter(params, "Case scenario", ["primary", "day_review_sensitivity"], "primary",
              {"primary": "All aligned reports", "day_review_sensitivity": "Exclude >180-day review flags"})
    parameter(params, "Case year", ["Both years", "2023", "2024"], "Both years")
    occupations = dict(zip(cases.soc_major.astype(str), cases.soc_major_label, strict=True))
    occupation_aliases = {code: (label if code == "unknown" else f"{code} | {label}")
                          for code, label in occupations.items()}
    parameter(params, "Case occupation", ["All occupations", *sorted(occupations)],
              "All occupations", occupation_aliases)
    mechanisms = dict(zip(cases.mechanism_group, cases.mechanism_label, strict=True))
    parameter(params, "Highlight mechanism", ["All mechanisms", *sorted(mechanisms)], "All mechanisms", mechanisms)
    annual_visible = ('[scenario] = [Parameters].[Annual scenario] AND '
                      '([Parameters].[Annual year] = "All years" OR STR([year]) = [Parameters].[Annual year] OR '
                      '([Parameters].[Annual year] = "2023–2024" AND [year] >= 2023 AND [year] <= 2024)) AND '
                      '([Parameters].[Annual size] = "All sizes" OR [size_group] = [Parameters].[Annual size])')
    case_visible = ('[scenario] = [Parameters].[Case scenario] AND '
                    '([Parameters].[Case year] = "Both years" OR STR([year]) = [Parameters].[Case year]) AND '
                    '([Parameters].[Case occupation] = "All occupations" OR [soc_major] = [Parameters].[Case occupation])')
    annual_formulas = {
        "Visible rows": (annual_visible, "boolean", True),
        "DART rate": ('IF SUM([hours_sum]) > 0 THEN 200000 * SUM([dart_case_count]) / SUM([hours_sum]) END', "real", False),
    }
    denominator = '{ FIXED : SUM(IF [Visible rows] THEN [case_report_count] ELSE 0 END) }'
    case_formulas = {
        "Visible rows": (case_visible, "boolean", True),
        "Report share": (f'IF MIN({denominator}) > 0 THEN SUM([case_report_count]) / MIN({denominator}) END', "real", False),
        "Highlighted mechanism": (('IF [Parameters].[Highlight mechanism] = "All mechanisms" OR '
                                   '[mechanism_group] = [Parameters].[Highlight mechanism] THEN '
                                   '"Selected" ELSE "Other mechanisms" END'), "string", True),
    }
    for prefix, caption in [("dafw", "DAFW"), ("djtr", "DJTR")]:
        blocked = ('{ FIXED : MAX(IF [Visible rows] AND [' + prefix
                   + '_days_status] = "blocked_review" THEN 1 ELSE 0 END) }')
        case_formulas[f"Accepted {caption} days"] = (
            (f'IF MIN({blocked}) = 0 AND SUM([{prefix}_days_known_report_count]) > 0 '
             f'THEN SUM([{prefix}_days_sum]) END'), "real", False)
    annual_source, annual_types = connection(datasources, "ss_annual", "Annual warehouse summaries",
                                             "annual_size_summary.csv", annual, annual_formulas)
    case_source, case_types = connection(datasources, "ss_cases", "Warehouse case profiles",
                                         "case_pattern_summary.csv", cases, case_formulas)
    sheets = node(book, "worksheets")
    annual_specs = [
        ("DART cases per 100 FTE by year", "DART rate", "year", "Line", "size_label"),
        ("Reported DART cases by year", "dart_case_count", "year", "Line", "size_label"),
        ("Pooled DART rate by size", "size_label", "DART rate", "Bar", None),
        ("Reporting establishment-years", "year", "establishment_year_count", "Bar", None),
    ]
    for name, rows, cols, mark, color in annual_specs:
        worksheet(sheets, name, annual_source, annual_types, params, rows, cols, mark, color)
    day_ready = not cases.dafw_days_status.eq("blocked_review").any()
    day_title = "Reported days away by mechanism" if day_ready else "Reports involving days away"
    consequence_field = "Accepted DAFW days" if day_ready else "outcome_dafw_count"
    case_specs = [
        ("Reported cases by mechanism", "mechanism_label", "case_report_count", "Bar", "Highlighted mechanism"),
        ("Share of selected reports", "mechanism_label", "Report share", "Bar", "Highlighted mechanism"),
        ("Occupations and mechanisms", "occupation_short", "mechanism_short", "Square", "case_report_count"),
        (day_title, "mechanism_label", consequence_field, "Bar", None),
    ]
    for name, rows, cols, mark, color in case_specs:
        worksheet(sheets, name, case_source, case_types, params, rows, cols, mark, color)
    dashboards = node(book, "dashboards")
    annual_title = "SafeShift | Annual warehouse patterns, 2016–2025"
    case_title = "SafeShift | Mechanisms and occupations, 2023–2024"
    dashboard(dashboards, annual_title, [x[0] for x in annual_specs],
              ["Annual scenario", "Annual year", "Annual size"],
              "DART = days-away + restricted/job-transfer cases. Rate = 200,000 × cases / hours. "
              "Size uses annual average employees. The 2025 primary rate is dominated by an extreme hours report. "
              "Use the exposure sensitivity comparison. Annual day totals remain under review.",
              [(annual_specs[0][0], ref("ss_annual", instance(annual_types, "size_label")[0]), 15500)])
    dashboard(dashboards, case_title, [x[0] for x in case_specs],
              ["Case scenario", "Case year", "Case occupation", "Highlight mechanism"],
              "Counts describe case reports, not unique people or occupation-specific risk. Unknown and Other are retained. "
              "Mechanisms are supplied machine classifications harmonized by source year. Highlighting leaves denominators unchanged. "
              "Day measures appear only when their source-matched policy permits publication.",
              [(case_specs[0][0], ref("ss_cases", instance(case_types, "Highlighted mechanism")[0]), 15500),
               (case_specs[2][0], ref("ss_cases", instance(case_types, "case_report_count")[0]), 55000)])
    methods_title = "SafeShift | Methods and limits"
    methods = node(dashboards, "dashboard", name=methods_title)
    node(methods, "style")
    node(methods, "size", maxheight=950, maxwidth=1440, minheight=950, minwidth=1440)
    zones = node(methods, "zones")
    root = node(zones, "zone", id=1, type="layout-basic", x=0, y=0, w=100000, h=100000)
    text_zone(root, 2, "SafeShift: descriptive evidence, reporting coverage and limitations", 2500, 1500, 95000, 8000, 23, True)
    text_zone(root, 3,
              "Research question\nHow have reported warehouse DART counts and rates varied by establishment size, "
              "and what mechanisms and occupation patterns appear in recent case reports?\n\n"
              "This project is descriptive, comparative and exploratory. It is not focused on predictive analysis.\n\n"
              "Two distinct populations\nAnnual summaries cover eligible reporting establishment-years from 2016–2025. "
              "Case profiles cover date-aligned warehouse reports from 2023–2024. Their counts are not expected to match.\n\n"
              "Rates and sizes\nDART rates use summed cases divided by summed reported hours, scaled by 200,000. "
              "They are never averages of site rates. Size refers to annual average employees.\n\n"
              "Sensitivity and quality\nExposure sensitivity excludes records outside the predeclared hours-per-employee review range. "
              "Case sensitivity excludes reports with individual or combined reported days above 180. These screens do not prove error. "
              "A withheld day measure is missing, not zero. Days are reported calendar days, not paid hours or costs.\n\n"
              "Classification and inference\nEvent-code meanings changed between years; the project uses a year-specific crosswalk. "
              "Occupation groups use SOC 2018 major groups; detailed SOC membership is not independently certified. "
              "SOC reassignment value 5 is retained. Unknown labels remain visible.\n\n"
              "Findings describe the available reporting population. They do not establish causality, national representativeness, "
              "or occupation-specific injury risk. Historical predictive work remains separate.",
              3000, 12000, 94000, 85000, 15)
    windows = node(book, "windows", source_height=30)
    for title, names in [(annual_title, [x[0] for x in annual_specs]),
                         (case_title, [x[0] for x in case_specs]), (methods_title, [])]:
        window = node(windows, "window", **{"class": "dashboard", "name": title, "maximized": "true"})
        viewpoints = node(window, "viewpoints")
        for name in names:
            point = node(viewpoints, "viewpoint", name=name)
            node(point, "zoom", type="entire-view")
        if names:
            node(window, "active", id=30)
    for name in [x[0] for x in annual_specs + case_specs]:
        window = node(windows, "window", **{"class": "worksheet", "name": name})
        node(node(window, "viewpoint"), "zoom", type="entire-view")
    ET.indent(book, space="  ")
    return ET.tostring(book, encoding="utf-8", xml_declaration=True)


def qa_reference(annual, cases):
    rows = []
    for scenario in ["primary", "exposure_sensitivity"]:
        for years, size in [([2016], None), ([2024], None), ([2025], None),
                            (sorted(annual.year.unique()), None),
                            ([2023, 2024], None), ([2023, 2024], "lt_50")]:
            selected = annual.loc[annual.scenario.eq(scenario) & annual.year.isin(years)]
            if size:
                selected = selected.loc[selected.size_group.eq(size)]
            hours, count = selected.hours_sum.sum(), selected.dart_case_count.sum()
            rows.append({"source": "annual", "scenario": scenario,
                         "years": ";".join(str(y) for y in years), "group": size or "All sizes",
                         "group_label": SIZE_LABELS.get(size, "All sizes"),
                         "expected_count": int(count), "expected_denominator": float(hours),
                         "expected_rate_or_share": 200000 * count / hours if hours > 0 else None,
                         "observed_value": "", "status": "reference_ready_tableau_check_pending"})
    for scenario in ["primary", "day_review_sensitivity"]:
        occupation = "53" if cases.soc_major.eq("53").any() else str(cases.soc_major.iloc[0])
        selections = [(years, None) for years in [[2023], [2024], [2023, 2024]]]
        selections += [([2024], occupation), ([2023, 2024], occupation)]
        for years, group in selections:
            selected = cases.loc[cases.scenario.eq(scenario) & cases.year.isin(years)]
            if group:
                selected = selected.loc[selected.soc_major.eq(group)]
            rows.append({"source": "cases", "scenario": scenario,
                         "years": ";".join(str(y) for y in years), "group": group or "All occupations",
                         "group_label": (str(selected.soc_major_label.iloc[0]) if group and len(selected)
                                         else group or "All occupations"),
                         "expected_count": int(selected.case_report_count.sum()),
                         "expected_denominator": int(selected.case_report_count.sum()),
                         "expected_rate_or_share": 1.0 if len(selected) else None,
                         "observed_value": "", "status": "reference_ready_tableau_check_pending"})
            denominator = int(selected.case_report_count.sum())
            by_mechanism = selected.groupby("mechanism_group", observed=True).case_report_count.sum()
            for mechanism, count in by_mechanism.items():
                rows.append({"source": "cases", "scenario": scenario,
                             "years": ";".join(str(y) for y in years),
                             "group": group or "All occupations", "mechanism_group": mechanism,
                             "expected_count": int(count), "expected_denominator": denominator,
                             "expected_rate_or_share": count / denominator if denominator else None,
                             "observed_value": "", "status": "reference_ready_tableau_check_pending"})
    return pd.DataFrame(rows)


def build(annual_path, case_path, output_dir, overwrite=False):
    output_dir = Path(output_dir)
    target = output_dir / "SafeShift_Research.twbx"
    if target.exists() and not overwrite:
        raise FileExistsError(f"Workbook already exists: {target}")
    annual = pd.read_csv(annual_path, keep_default_na=True)
    cases = pd.read_csv(case_path, dtype={"soc_major": str}, keep_default_na=True)
    require(len(cases) > 0, "No eligible case reports are available for a Tableau case view")
    require(not (set(ANNUAL_REQUIRED) - set(annual)), "Annual export schema incomplete")
    require(not (set(CASE_REQUIRED) - set(cases)), "Case export schema incomplete")
    require(not annual.duplicated(["year", "size_group", "scenario"]).any(), "Repeated annual keys")
    require(not cases.duplicated(["year", "mechanism_group", "soc_major", "scenario"]).any(), "Repeated case keys")
    require(set(annual.scenario) <= {"primary", "exposure_sensitivity"}, "Unexpected annual scenario")
    require(set(cases.scenario) <= {"primary", "day_review_sensitivity"}, "Unexpected case scenario")
    for frame in [annual, cases]:
        require(not any(any(word in name.lower() for word in ["narrative", "establishment_id", "case_number",
                        "street_address", "ein", "job_description"]) for name in frame),
                "Identifying or narrative fields cannot enter the workbook")
        for prefix in ["dafw", "djtr"]:
            require(frame.loc[frame[f"{prefix}_days_status"].eq("blocked_review"),
                               f"{prefix}_days_sum"].isna().all(), "Blocked day values are not blank")
    annual["size_label"] = annual.size_group.map(SIZE_LABELS)
    require(annual.size_label.notna().all(), "Unknown annual size group")
    short_mechanisms = {"transportation": "Transport", "falls_slips_trips": "Falls / trips",
                        "harmful_exposure": "Exposure", "object_equipment_contact": "Contact",
                        "overexertion_bodily_reaction": "Overexertion",
                        "other_reported_mechanism": "Other", "unknown_missing_mechanism": "Unknown"}
    cases["mechanism_short"] = cases.mechanism_group.map(short_mechanisms)
    require(cases.mechanism_short.notna().all(), "Unknown mechanism group in dashboard")
    cases["occupation_short"] = [
        ("Unknown occupation" if code == "unknown" else code + " · "
         + label.removesuffix(" Occupations").replace(" and ", " & ")[:31])
        for code, label in zip(cases.soc_major, cases.soc_major_label, strict=True)]
    xml = workbook_xml(annual, cases)
    parsed = ET.fromstring(xml)
    require(len(parsed.findall(".//worksheets/worksheet")) == 8, "Missing native worksheets")
    for sheet in parsed.findall(".//worksheets/worksheet"):
        require(sheet.find(".//filter") is not None, "Worksheet lacks mandatory row filter")
    annual_bytes = annual.to_csv(index=False).encode()
    case_bytes = cases.to_csv(index=False).encode()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "Data").mkdir(exist_ok=True)
    (output_dir / "Data/annual_size_summary.csv").write_bytes(annual_bytes)
    (output_dir / "Data/case_pattern_summary.csv").write_bytes(case_bytes)
    (output_dir / "SafeShift_Research.twb").write_bytes(xml)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SafeShift_Research.twb", xml)
        archive.writestr("Data/annual_size_summary.csv", annual_bytes)
        archive.writestr("Data/case_pattern_summary.csv", case_bytes)
    with zipfile.ZipFile(target) as archive:
        require(archive.testzip() is None, "Packaged workbook CRC failed")
    references = qa_reference(annual, cases)
    references.to_csv(output_dir / "tableau_qa_references.csv", index=False)
    inventory = {"scope": "Packaged workbook aggregate sources", "row_level_facts_included": False,
                 "annual": {"rows": len(annual), "columns": list(annual)},
                 "cases": {"rows": len(cases), "columns": list(cases)},
                 "check": "No names, EINs, addresses, narratives, free-text jobs or source case IDs are included"}
    (output_dir / "public_export_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    specification = ["# SafeShift Tableau release", "",
                     "Open SafeShift_Research.twbx in Tableau Desktop/Public. Application version and display checks are pending.", "",
                     ("Annual grain: year × annual-average-employment size × scenario. "
                     "Case grain: aligned source year × mechanism × SOC major group × scenario. "
                     "The sources remain separate, with no fact-table relationship or join."), "",
                     ("Refresh: rerun the source case analysis, then `uv run --locked python -m "
                     "src.analysis.tableau_release --overwrite`. See docs/research_v2/tableau_handoff.md for QA."), "",
                     "## Parameters", ""]
    for field in parsed.findall("datasources/datasource[@name='Parameters']/column"):
        choices = [member.attrib.get("alias", member.attrib["value"])
                   for member in field.findall("members/member")]
        specification.append(f"- {field.attrib['caption']}: " + "; ".join(choices))
    specification += ["", "## Exact workbook calculations", ""]
    for source in parsed.findall("datasources/datasource"):
        for field in source.findall("column"):
            calculation = field.find("calculation")
            if calculation is not None and source.attrib["name"] != "Parameters":
                specification += [f"{source.attrib['caption']} — {field.attrib['name']}", "",
                                  "```text", calculation.attrib["formula"], "```", ""]
    specification += ["## Verification and interpretation", "",
                      ("Compare displayed counts exactly and unrounded rates/shares within 0.000001 against "
                      "tableau_qa_references.csv. Observed values remain blank until actual Tableau readback. "
                      "Record Tableau version, opening result, controls, legends, laptop layout and no-data selections. "
                      "Mechanism highlighting must leave share denominators unchanged. Never combine scenarios."), "",
                      ("Annual day totals remain blocked. Case day totals require a source-matched accepted policy; "
                      "otherwise the consequence panel shows report frequency. Unknown groups remain visible. "
                      "The workbook describes reporting patterns and does not predict future injuries or establish occupation risk."), ""]
    (output_dir / "README.md").write_text("\n".join(specification))
    manifest = {"created_utc": datetime.now(UTC).isoformat(), "worksheets": 8, "dashboards": 3,
                "annual_source_sha256": hashlib.sha256(Path(annual_path).read_bytes()).hexdigest(),
                "case_source_sha256": hashlib.sha256(Path(case_path).read_bytes()).hexdigest(),
                "workbook_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "checks": {"xml_well_formed": True, "packaged_sources_present": True,
                           "mandatory_scenario_filters": True, "no_fact_table_join": True,
                           "identifying_fields_excluded": True},
                "tableau_application_check": "PENDING: open in Tableau Desktop/Public on the Mac",
                "tableau_displayed_value_checks": "PENDING: compare with tableau_qa_references.csv"}
    (output_dir / "tableau_build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Native packaged workbook: {target}")
    print("Package/XML checks passed. Tableau application opening and displayed-value checks remain pending.")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual", type=Path, default=Path("data/processed/research_v2/annual_size_summary.csv"))
    parser.add_argument("--cases", type=Path, default=Path("data/processed/research_v2/case_pattern_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("tableau/research_v2"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    build(args.annual, args.cases, args.output_dir, args.overwrite)


if __name__ == "__main__":
    main()
