# EPA ECHO Facilities Dashboard

A Streamlit dashboard of EPA-regulated facilities in ten high-tech and life-science
industries, built from **EPA ECHO** (Enforcement and Compliance History Online).

| NAICS  | Industry |
|--------|----------|
| 334413 | Semiconductor Manufacturing |
| 33591  | Battery Manufacturing (also catches 335910 / 335911 / 335912) |
| 518210 | Data Centers |
| 325411 | Medicinal & Botanical Manufacturing |
| 325412 | Pharmaceutical Preparation Manufacturing |
| 325413 | In-Vitro Diagnostic Substance Manufacturing |
| 325414 | Biological Product Manufacturing |
| 424210 | Drugs & Druggists' Sundries Wholesalers |
| 621511 | Medical Laboratories |
| 621512 | Diagnostic Imaging Centers |

## Features

- Sidebar filters: EPA region, state, and industry category (all multi-select), plus an "active only" toggle
- Top-line metric: total matching facilities (plus states, significant non-compliance count, total penalties)
- Interactive map of facilities (latitude/longitude, hover for name and industry)
- Bar charts of facility counts by state and by industry category
- Data table with a **Download CSV** button for the filtered rows

## How the data works

No data files live in this repo. On first load the app calls the
[ECHO REST API](https://echo.epa.gov/tools/web-services/facility-search-all-data):

1. `echo_rest_services.get_facilities` with `p_ncs=334413,33591,518210,…` runs the
   NAICS filter on EPA's servers and returns a QueryID.
2. `echo_rest_services.get_download` streams every matching row as CSV (~12,000
   facilities, ~3 MB, a few seconds).

ECHO stores several space-separated NAICS codes per facility (e.g. `33422 334413`).
The app re-checks every code with a **prefix match**, so a facility matches if *any*
of its codes starts with one of the ten values above. A facility can belong to more
than one category; the industry bar chart counts it in each.

**Weekly refresh:** the result is cached with `st.cache_data(ttl=7 days)`, so the app
automatically pulls fresh ECHO data once a week with no manual step.

**Fallback:** if the API is down, the app downloads EPA's weekly
[ECHO Exporter](https://echo.epa.gov/tools/data-downloads) zip and filters it in
chunks. This is slower (the file is ~450 MB) and only used when the API fails.
The sidebar shows which source was used and when it was fetched.

## Project structure

```
echo-dashboard/
├── app.py               # Streamlit UI
├── echo_data.py         # ECHO API client, exporter fallback, NAICS matching
├── requirements.txt
├── .streamlit/config.toml
├── .gitignore           # excludes CSV/ZIP/XLSX and other large data files
└── README.md
```

## Run locally

```bash
cd echo-dashboard
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

---

## Step 1 — Push to GitHub

1. Sign in at [github.com](https://github.com) and click **New repository**.
   Name it (e.g. `echo-dashboard`), choose **Public** (Community Cloud's free tier
   needs public repos, or connect a private repo with GitHub permissions), and
   **do not** add a README/.gitignore (this project already has them). Click **Create repository**.
2. In a terminal, from inside the `echo-dashboard` folder:

   ```bash
   git init
   git add .
   git commit -m "Initial commit: ECHO facilities dashboard"
   git branch -M main
   git remote add origin https://github.com/<your-username>/echo-dashboard.git
   git push -u origin main
   ```

3. Refresh the GitHub page and confirm you see `app.py`, `echo_data.py`,
   `requirements.txt`, `README.md`, `.gitignore`, and `.streamlit/` — and **no** `.csv` or `.zip` files.
   (Run `git status` before committing if you want to double-check what will be added.)

## Step 2 — Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
   (authorize Streamlit to access your repositories when prompted).
2. Click **Create app** → **Deploy a public app from GitHub** (or "Yup, I have an app").
3. Fill in:
   - **Repository:** `<your-username>/echo-dashboard`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL (optional):** pick a custom subdomain, e.g. `echo-facilities`
4. (Optional) **Advanced settings** → choose Python 3.12. No secrets are needed — the ECHO API is public.
5. Click **Deploy**. The first build installs `requirements.txt` (1–3 minutes), then
   the app fetches ECHO data (a few seconds).
6. Copy the URL (e.g. `https://echo-facilities.streamlit.app`) — that's your shareable link.

### Updating the app

Any `git push` to `main` redeploys automatically. Data refreshes on its own every
7 days; to force an immediate refresh, open the app menu (⋮, top right) → **Clear cache**
and rerun, or **Reboot app** from the Community Cloud dashboard.

### Notes

- Community Cloud apps sleep after a period of no traffic; the first visitor after
  that waits a few seconds while it wakes up and (if the cache expired) refetches.
- Data source: U.S. EPA ECHO, https://echo.epa.gov. Counts reflect EPA's facility
  registry and may include inactive or duplicate-site records (use the "Active
  facilities only" filter to narrow).
