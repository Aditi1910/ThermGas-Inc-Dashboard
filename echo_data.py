"""Data access for the ECHO facilities dashboard.

Primary source: the EPA ECHO REST API (echo_rest_services).
  1. get_facilities  -> runs the NAICS-filtered query server-side, returns a QueryID
  2. get_download    -> streams every matching row for that QueryID as CSV

Fallback source: EPA's weekly ECHO Exporter flat file (a ~450 MB zip). It is only
used if the API is unreachable, and it is streamed + filtered in chunks so the
full file never has to sit in memory or on disk in the repo.

API docs: https://echo.epa.gov/tools/web-services/facility-search-all-data
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import requests

API_BASE = "https://echodata.epa.gov/echo/echo_rest_services"
EXPORTER_URL = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"

# Exactly the 10 NAICS codes in scope, with friendly labels.
# Matching is by PREFIX, so "33591" also catches 335910 / 335911 / 335912.
NAICS_LABELS: dict[str, str] = {
    "334413": "Semiconductor Manufacturing",
    "33591": "Battery Manufacturing",
    "518210": "Data Centers",
    "325411": "Medicinal & Botanical Manufacturing",
    "325412": "Pharmaceutical Preparation Manufacturing",
    "325413": "In-Vitro Diagnostic Substance Manufacturing",
    "325414": "Biological Product Manufacturing",
    "424210": "Drugs & Druggists' Sundries Wholesalers",
    "621511": "Medical Laboratories",
    "621512": "Diagnostic Imaging Centers",
}

# ECHO "all data" column IDs (from echo_rest_services.metadata) -> output column names
API_COLUMNS: dict[int, str] = {
    1: "FacName",
    2: "FacStreet",
    3: "FacCity",
    4: "FacState",
    5: "FacZip",
    6: "RegistryID",
    7: "FacCounty",
    8: "FacEPARegion",
    17: "FacNAICSCodes",
    18: "FacNAICSDescs",
    19: "FacLat",
    20: "FacLong",
    36: "FacSNCFlg",
    38: "FacComplianceStatus",
    43: "FacInspectionCount",
    45: "FacDateLastInspection",
    56: "FacFormalActionCount",
    62: "FacTotalPenalties",
    97: "FacActiveFlag",
}

# Same fields in the ECHO Exporter flat file -> API-style names
EXPORTER_COLUMNS: dict[str, str] = {
    "FAC_NAME": "FacName",
    "FAC_STREET": "FacStreet",
    "FAC_CITY": "FacCity",
    "FAC_STATE": "FacState",
    "FAC_ZIP": "FacZip",
    "REGISTRY_ID": "RegistryID",
    "FAC_COUNTY": "FacCounty",
    "FAC_EPA_REGION": "FacEPARegion",
    "FAC_NAICS_CODES": "FacNAICSCodes",
    "FAC_LAT": "FacLat",
    "FAC_LONG": "FacLong",
    "FAC_SNC_FLG": "FacSNCFlg",
    "FAC_COMPLIANCE_STATUS": "FacComplianceStatus",
    "FAC_INSPECTION_COUNT": "FacInspectionCount",
    "FAC_DATE_LAST_INSPECTION": "FacDateLastInspection",
    "FAC_FORMAL_ACTION_COUNT": "FacFormalActionCount",
    "FAC_TOTAL_PENALTIES": "FacTotalPenalties",
    "FAC_ACTIVE_FLAG": "FacActiveFlag",
}

TIMEOUT = 300  # seconds; the download of ~12k rows normally takes < 15 s


def match_categories(naics_field: object) -> list[str]:
    """Return the friendly labels whose NAICS prefix matches any code in the field.

    ECHO stores multiple codes per facility separated by spaces (sometimes commas),
    e.g. "33422 334413". A facility can therefore match more than one category.
    """
    if not isinstance(naics_field, str) or not naics_field.strip():
        return []
    codes = naics_field.replace(",", " ").split()
    return [
        label
        for prefix, label in NAICS_LABELS.items()
        if any(code.startswith(prefix) for code in codes)
    ]


def fetch_from_api() -> pd.DataFrame:
    """Run the NAICS query on the ECHO REST API and download all matching rows."""
    qcolumns = ",".join(str(c) for c in API_COLUMNS)
    params = {
        "output": "JSON",
        "p_ncs": ",".join(NAICS_LABELS),  # server-side NAICS filter (prefix match)
        "qcolumns": qcolumns,
        "responseset": 1,  # we only need the QueryID here, not the rows
    }
    r = requests.get(f"{API_BASE}.get_facilities", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    results = r.json()["Results"]
    if "QueryID" not in results:
        raise RuntimeError(f"ECHO API error: {results.get('Error') or results}")
    qid = results["QueryID"]

    r = requests.get(
        f"{API_BASE}.get_download",
        params={"output": "CSV", "qid": qid, "qcolumns": qcolumns},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), dtype=str)


def fetch_from_exporter() -> pd.DataFrame:
    """Fallback: stream EPA's weekly ECHO Exporter zip and keep only matching rows."""
    with requests.get(EXPORTER_URL, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        for chunk in r.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
    with zipfile.ZipFile(buf) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        keep = []
        with zf.open(name) as fh:
            for chunk in pd.read_csv(
                fh,
                dtype=str,
                usecols=lambda c: c in EXPORTER_COLUMNS,
                chunksize=200_000,
                encoding="latin-1",
            ):
                mask = chunk["FAC_NAICS_CODES"].map(lambda v: bool(match_categories(v)))
                keep.append(chunk[mask])
    return pd.concat(keep, ignore_index=True).rename(columns=EXPORTER_COLUMNS)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Type conversion, category tagging, and a final client-side prefix filter."""
    df = df.copy()
    df["Categories"] = df["FacNAICSCodes"].map(match_categories)
    df = df[df["Categories"].map(len) > 0]  # guarantees exact prefix semantics
    df["Industry"] = df["Categories"].map(lambda c: "; ".join(c))

    df["FacLat"] = pd.to_numeric(df["FacLat"], errors="coerce")
    df["FacLong"] = pd.to_numeric(df["FacLong"], errors="coerce")
    for col in ("FacInspectionCount", "FacFormalActionCount"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "FacTotalPenalties" in df:
        df["FacTotalPenalties"] = pd.to_numeric(
            df["FacTotalPenalties"].astype(str).str.replace(r"[$,]", "", regex=True),
            errors="coerce",
        ).fillna(0.0)
    if "FacEPARegion" in df:
        region = pd.to_numeric(df["FacEPARegion"], errors="coerce")
        df["FacEPARegion"] = region.map(lambda x: f"Region {int(x)}" if pd.notna(x) else "Unknown")
    df["FacState"] = df["FacState"].fillna("Unknown").str.strip().str.upper()
    return df.drop_duplicates("RegistryID").reset_index(drop=True)


def load_facilities() -> tuple[pd.DataFrame, str]:
    """Return (clean dataframe, name of the source used). Prefers the API."""
    try:
        return clean(fetch_from_api()), "ECHO REST API (get_facilities + get_download)"
    except Exception as api_err:  # noqa: BLE001 - any API failure triggers fallback
        try:
            return clean(fetch_from_exporter()), f"ECHO Exporter flat file (API failed: {api_err})"
        except Exception as file_err:  # noqa: BLE001
            raise RuntimeError(
                f"Could not load ECHO data. API error: {api_err}; "
                f"Exporter fallback error: {file_err}"
            ) from file_err
