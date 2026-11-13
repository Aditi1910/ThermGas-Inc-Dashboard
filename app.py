"""EPA ECHO facilities dashboard - semiconductors, batteries, data centers, pharma & labs."""

from datetime import datetime, timezone

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from echo_data import NAICS_LABELS, load_facilities

ONE_WEEK = 7 * 24 * 60 * 60  # seconds

# Palette from the ThermGAS client presentation (also set in .streamlit/config.toml)
PURPLE, BEIGE, GREY, WHITE = "#7A5C99", "#ECE6DD", "#72768A", "#FFFFFF"

# EPA's 10 regions: (regional office, states/territories, short description)
REGION_INFO: dict[str, tuple[str, str, str]] = {
    "Region 1": ("Boston, MA", "CT, ME, MA, NH, RI, VT",
                 "New England; a major biotech and pharma hub around Boston/Cambridge."),
    "Region 2": ("New York, NY", "NJ, NY, Puerto Rico, U.S. Virgin Islands",
                 "Dense pharma manufacturing corridor in New Jersey and Puerto Rico."),
    "Region 3": ("Philadelphia, PA", "DE, DC, MD, PA, VA, WV",
                 "Mid-Atlantic; home to Northern Virginia's 'Data Center Alley' and Maryland biotech."),
    "Region 4": ("Atlanta, GA", "AL, FL, GA, KY, MS, NC, SC, TN",
                 "Southeast; North Carolina's Research Triangle pharma and fast-growing battery plants."),
    "Region 5": ("Chicago, IL", "IL, IN, MI, MN, OH, WI",
                 "Great Lakes industrial belt; strong pharma, medical-device and EV battery activity."),
    "Region 6": ("Dallas, TX", "AR, LA, NM, OK, TX",
                 "South Central; large Texas semiconductor fabs (Austin, Dallas) and data centers."),
    "Region 7": ("Lenexa, KS (Kansas City)", "IA, KS, MO, NE",
                 "Midwest plains; animal-health and biologics manufacturing corridor."),
    "Region 8": ("Denver, CO", "CO, MT, ND, SD, UT, WY",
                 "Mountains & Plains; Colorado/Utah tech and semiconductor sites."),
    "Region 9": ("San Francisco, CA", "AZ, CA, HI, NV, Pacific territories",
                 "Pacific Southwest; Silicon Valley, Arizona chip fabs, and California biotech."),
    "Region 10": ("Seattle, WA", "AK, ID, OR, WA",
                  "Pacific Northwest; Oregon/Idaho semiconductor fabs and large data centers."),
}

st.set_page_config(page_title="ThermGas Inc. Facilities Dashboard", page_icon="🏭", layout="wide")


@st.cache_data(ttl=ONE_WEEK, show_spinner="Pulling the latest facility data from EPA ECHO…")
def get_data() -> tuple[pd.DataFrame, str, str]:
    df, source = load_facilities()
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return df, source, fetched


try:
    data, source, fetched_at = get_data()
except Exception as err:  # noqa: BLE001
    st.error(f"Could not load data from EPA ECHO right now. Please try again later.\n\n{err}")
    st.stop()

# ---------------------------------------------------------------- sidebar filters
st.sidebar.header("Filters")

regions = sorted(data["FacEPARegion"].unique(), key=lambda r: (len(r), r))
sel_regions = st.sidebar.multiselect("EPA region", regions, placeholder="All regions")
for region in sel_regions:
    if region in REGION_INFO:
        office, states_txt, blurb = REGION_INFO[region]
        with st.sidebar.container(border=True):
            st.markdown(
                f"<span style='color:{PURPLE}'><b>{region} · {office}</b></span>  \n{states_txt}  \n"
                f"<span style='color:{GREY}'><i>{blurb}</i></span>",
                unsafe_allow_html=True,
            )

state_pool = data if not sel_regions else data[data["FacEPARegion"].isin(sel_regions)]
states = sorted(state_pool["FacState"].unique())
sel_states = st.sidebar.multiselect("State", states, placeholder="All states")

industries = list(NAICS_LABELS.values())
sel_industries = st.sidebar.multiselect(
    "Industry category",
    industries,
    format_func=lambda lbl: f"{lbl} ({[k for k, v in NAICS_LABELS.items() if v == lbl][0]})",
    placeholder="All industries",
)

active_only = st.sidebar.checkbox("Active facilities only", value=False)

st.sidebar.divider()
st.sidebar.caption(f"Source: {source}")
st.sidebar.caption(f"Last fetched: {fetched_at} · refreshes automatically every 7 days")

# ---------------------------------------------------------------- apply filters
df = data
if sel_regions:
    df = df[df["FacEPARegion"].isin(sel_regions)]
if sel_states:
    df = df[df["FacState"].isin(sel_states)]
if sel_industries:
    df = df[df["Categories"].map(lambda cats: any(c in sel_industries for c in cats))]
if active_only:
    df = df[df["FacActiveFlag"] == "Y"]

# ---------------------------------------------------------------- header + metrics
st.title("ThermGas Inc. Facilities Dashboard")
st.caption(
    "Facilities regulated by the U.S. EPA in semiconductor, battery, data center, "
    "pharmaceutical, biologics, drug wholesale, and medical lab / imaging industries."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Matching facilities", f"{len(df):,}")
c2.metric("States", f"{df['FacState'].nunique():,}")
pen = df["FacTotalPenalties"].sum()
c3.metric("Significant violators", f"{(df['FacSNCFlg'] == 'Y').sum():,}",
          help="Facilities flagged in Significant Non-Compliance (SNC) by EPA")
c4.metric("Total penalties", f"${pen / 1e6:,.1f}M" if pen >= 1e6 else f"${pen:,.0f}",
          help=f"${pen:,.0f} in federal penalties over the last 5 years")

if df.empty:
    st.info("No facilities match the current filters.")
    st.stop()

# ---------------------------------------------------------------- map
st.subheader("Facility map")
geo = df.dropna(subset=["FacLat", "FacLong"])
geo = geo[geo["FacLat"].between(-90, 90) & geo["FacLong"].between(-180, 180)]
st.pydeck_chart(
    pdk.Deck(
        map_style=None,  # uses Streamlit's theme-aware basemap
        initial_view_state=pdk.ViewState(
            latitude=float(geo["FacLat"].median()) if len(geo) else 39.5,
            longitude=float(geo["FacLong"].median()) if len(geo) else -98.35,
            zoom=3 if not sel_states else 5,
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=geo[["FacName", "FacCity", "FacState", "Industry", "FacLat", "FacLong"]],
                get_position="[FacLong, FacLat]",
                get_fill_color=[122, 92, 153, 190],  # deck purple
                get_radius=4000,
                radius_min_pixels=2,
                radius_max_pixels=8,
                pickable=True,
            )
        ],
        tooltip={"text": "{FacName}\n{FacCity}, {FacState}\n{Industry}"},
    ),
    height=480,
)
st.caption(f"{len(geo):,} of {len(df):,} facilities have usable coordinates.")

# ---------------------------------------------------------------- bar charts
st.subheader("Facilities by state")
by_state = df["FacState"].value_counts().rename_axis("State").reset_index(name="Facilities")
st.altair_chart(
    alt.Chart(by_state)
    .mark_bar(color=PURPLE, cornerRadiusEnd=3)
    .encode(
        x=alt.X("State:N", sort="-y", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Facilities:Q"),
        tooltip=["State", "Facilities"],
    )
    .properties(height=320),
    width="stretch",
)

st.subheader("Facilities by industry category")
by_ind = df["Categories"].explode().value_counts().rename_axis("Industry").reset_index(name="Facilities")
if sel_industries:
    by_ind = by_ind[by_ind["Industry"].isin(sel_industries)]
st.altair_chart(
    alt.Chart(by_ind)
    .mark_bar(color=PURPLE, cornerRadiusEnd=3)
    .encode(
        x=alt.X("Facilities:Q"),
        y=alt.Y("Industry:N", sort="-x", title=None, axis=alt.Axis(labelLimit=300)),
        tooltip=["Industry", "Facilities"],
    )
    .properties(height=34 * len(by_ind) + 40),
    width="stretch",
)
st.caption("A facility with several matching NAICS codes is counted in each of its categories.")

# ---------------------------------------------------------------- table + download
st.subheader("Facility data")
table = df.drop(columns=["Categories"]).rename(
    columns={
        "FacName": "Facility",
        "FacStreet": "Street",
        "FacCity": "City",
        "FacState": "State",
        "FacZip": "ZIP",
        "RegistryID": "FRS Registry ID",
        "FacCounty": "County",
        "FacEPARegion": "EPA Region",
        "FacNAICSCodes": "NAICS Codes",
        "FacNAICSDescs": "NAICS Descriptions",
        "FacLat": "Latitude",
        "FacLong": "Longitude",
        "FacSNCFlg": "Significant Non-Compliance",
        "FacComplianceStatus": "Compliance Status",
        "FacInspectionCount": "Inspections (5 yr)",
        "FacDateLastInspection": "Last Inspection",
        "FacFormalActionCount": "Formal Actions (5 yr)",
        "FacTotalPenalties": "Total Penalties ($)",
        "FacActiveFlag": "Active",
    }
)
first = ["Facility", "Industry", "City", "State", "EPA Region", "NAICS Codes"]
table = table[first + [c for c in table.columns if c not in first]]

st.dataframe(table, width="stretch", hide_index=True)
st.download_button(
    "Download filtered data as CSV",
    data=table.to_csv(index=False).encode("utf-8"),
    file_name="echo_facilities_filtered.csv",
    mime="text/csv",
)

st.caption(
    "Data: U.S. EPA Enforcement and Compliance History Online (ECHO), "
    "https://echo.epa.gov. NAICS matching uses code prefixes "
    "(e.g. 33591 includes 335911 and 335912)."
)
