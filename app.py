import re
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

APP_TITLE = "NAV price"
AIA_DIRECTORY = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price"
AIA_FUNDS = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
TIMEOUT = 25

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1450px;padding-top:1.5rem}
.hero{padding:1.3rem 1.5rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;
background:linear-gradient(120deg,rgba(220,38,38,.10),rgba(59,130,246,.06))}
.small-muted{opacity:.7;font-size:.88rem}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero">
<h1 style="margin:0">📈 {APP_TITLE}</h1>
<p>AIA Singapore ILP factsheets · underlying funds · reported performance</p>
<p class="small-muted">Factsheet-first research tool. Reporting dates are displayed; unavailable returns are left blank.</p>
</div>
""", unsafe_allow_html=True)

@st.cache_data(ttl=21600, show_spinner=False)
def get_page(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def full_url(href, base):
    return urljoin(base, href)

@st.cache_data(ttl=21600, show_spinner=False)
def discover_funds():
    html = get_page(AIA_DIRECTORY)
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    base_path = urlparse(AIA_DIRECTORY).path.rstrip("/")
    for a in soup.select("a[href]"):
        url = full_url(a.get("href", ""), AIA_DIRECTORY)
        path = urlparse(url).path.rstrip("/")
        if path.startswith(base_path + "/"):
            slug = path[len(base_path)+1:]
            if not slug or "/" in slug or any(k in slug.lower() for k in ["comparison", "quickrank", "screener"]):
                continue
            name = clean(a.get_text(" ", strip=True)) or slug.replace("-", " ").title()
            result[url] = {"name": name, "url": url}
    return sorted(result.values(), key=lambda x: x["name"].lower())

def extract_tables(soup):
    tables = []
    for table in soup.find_all("table"):
        try:
            rows = []
            for tr in table.find_all("tr"):
                cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        except Exception:
            pass
    return tables

def find_fact_pairs(soup):
    pairs = {}
    for table in extract_tables(soup):
        for row in table:
            if len(row) >= 2:
                key = row[0].strip().rstrip(":")
                value = " | ".join(row[1:]).strip()
                if key and value and len(key) < 100:
                    pairs[key] = value
    lines = [clean(x) for x in soup.get_text("\n").splitlines() if clean(x)]
    wanted = ["Investment objective", "Underlying investment", "Underlying Funds", "Benchmark",
              "Manager of ILP fund", "Fund currency", "Valuation date as of", "Risk classification"]
    for i, line in enumerate(lines):
        if any(line.lower() == x.lower() for x in wanted) and i + 1 < len(lines):
            pairs.setdefault(line, lines[i+1])
    return pairs

def find_docs(soup, page_url):
    docs = []
    for a in soup.select("a[href]"):
        label = clean(a.get_text(" ", strip=True))
        href = full_url(a.get("href", ""), page_url)
        test = (label + " " + href).lower()
        if ".pdf" in href.lower() or any(x in test for x in ["factsheet", "fund summary", "investment fund summary", "product summary"]):
            if href.lower().endswith(".pdf") or "factsheet" in test or "fund summary" in test or "investment fund summary" in test:
                docs.append({"label": label or "PDF / fund document", "url": href})
    seen = set()
    return [d for d in docs if not (d["url"] in seen or seen.add(d["url"]))]

def underlying_names(pairs):
    candidates = []
    for key, value in pairs.items():
        if "underlying" in key.lower():
            # Some pages place a long list in a single cell.
            for part in re.split(r"\s*[;•]\s*|\s*\n\s*| \| ", value):
                part = clean(part)
                if "AIA" in part and ("Fund" in part or "Bond" in part or "Income" in part or "Equity" in part):
                    part = re.sub(r"^(?:[-–]\s*)+", "", part)
                    if part not in candidates:
                        candidates.append(part)
    # Also scan all visible page text for known-style fund names after "Underlying Funds".
    return candidates

@st.cache_data(ttl=21600, show_spinner=False)
def load_fund(url, fallback_name):
    try:
        soup = BeautifulSoup(get_page(url), "html.parser")
        h1 = soup.find("h1")
        name = clean(h1.get_text(" ", strip=True)) if h1 else fallback_name
        pairs = find_fact_pairs(soup)
        docs = find_docs(soup, url)
        underlying = underlying_names(pairs)
        return {"name": name, "url": url, "facts": pairs, "documents": docs,
                "underlying": underlying, "error": None}
    except Exception as e:
        return {"name": fallback_name, "url": url, "facts": {}, "documents": [],
                "underlying": [], "error": str(e)}

st.sidebar.header("Data settings")
if st.sidebar.button("Refresh AIA pages", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
st.sidebar.markdown(f"[AIA fund-price directory]({AIA_DIRECTORY})")
st.sidebar.markdown(f"[AIA fund information]({AIA_FUNDS})")
st.sidebar.caption("Page cache: up to 6 hours. Refresh to request fresh pages.")

st.info("This version focuses on what each AIA ILP fund says it invests in and links to the latest available factsheet/summary. The parent fund's factsheet may report only the parent fund's returns—not the separate performance of each underlying fund. Where a separate underlying-fund return is not disclosed, the app will not infer it.")

try:
    funds = discover_funds()
except Exception as e:
    st.error(f"Could not read AIA's fund directory: {e}")
    st.markdown(f"Open the official directory manually: {AIA_DIRECTORY}")
    st.stop()

if not funds:
    st.warning("No fund links were detected in the directory HTML. AIA may have changed its page structure.")
    st.stop()

left, right = st.columns([1, 2])
with left:
    query = st.text_input("Search ILP funds", placeholder="e.g. Global Dynamic Income")
    filtered = [f for f in funds if query.lower() in f["name"].lower()] if query else funds
    chosen = st.selectbox("Choose an AIA ILP fund", filtered, format_func=lambda f: f["name"])
    load = st.button("Load fund factsheet details", type="primary", use_container_width=True)
with right:
    st.metric("Fund pages discovered", len(funds))
    st.caption("Availability can vary by the policy. Confirm against the product summary for the relevant plan.")

if "selected_fund_data" not in st.session_state:
    st.session_state["selected_fund_data"] = None
if load:
    with st.spinner("Reading the selected AIA fund page and document links…"):
        st.session_state["selected_fund_data"] = load_fund(chosen["url"], chosen["name"])

data = st.session_state.get("selected_fund_data")
if data:
    st.divider()
    st.subheader(data["name"])
    st.markdown(f"**AIA fund page:** [{data['url']}]({data['url']})")
    if data["error"]:
        st.error(data["error"])
    facts = data["facts"]
    if facts:
        st.markdown("### What does the ILP fund track or invest in?")
        objective = next((v for k,v in facts.items() if "objective" in k.lower()), None)
        benchmark = next((v for k,v in facts.items() if "benchmark" in k.lower()), None)
        if objective:
            st.markdown("**Investment objective**")
            st.write(objective)
        st.write("**Benchmark**")
        st.write(benchmark or "Not detected in the page. Check the latest factsheet.")
        selected_facts = [{"Field": k, "Value": v} for k,v in facts.items()
                          if any(w in k.lower() for w in ["underlying", "benchmark", "currency", "risk", "manager", "fee", "objective"])]
        if selected_facts:
            st.dataframe(pd.DataFrame(selected_facts), use_container_width=True, hide_index=True)
    else:
        st.warning("No structured facts were detected in the page HTML. Use the official documents below.")

    st.markdown("### Underlying funds listed by AIA")
    if data["underlying"]:
        st.dataframe(pd.DataFrame({"Underlying fund": data["underlying"]}), use_container_width=True, hide_index=True)
    else:
        st.info("The underlying-fund list was not reliably extracted from the page HTML. Open the official factsheet/summary below; do not treat this as proof that no underlying funds exist.")

    st.markdown("### Latest available factsheets / summaries")
    if data["documents"]:
        for doc in data["documents"]:
            st.markdown(f"- [{doc['label']}]({doc['url']})")
    else:
        st.info("No document links were detected automatically. Open the official AIA fund page to access available documents.")

    st.markdown("### Underlying-fund returns")
    st.write("This table will only be populated when a current official factsheet explicitly reports performance for the underlying funds. The parent ILP factsheet often reports the parent fund's performance instead.")
    st.dataframe(pd.DataFrame(columns=["Underlying fund", "Return period", "Reported return", "As-of date", "Official source"]), use_container_width=True, hide_index=True)
    st.caption("Next implementation step: download and parse the linked PDFs, identify each underlying fund's own latest factsheet, and extract its stated performance table with the report date and source link.")

st.divider()
with st.expander("How returns will be displayed"):
    st.markdown("""
- **Factsheet return** means the performance figure printed in the latest official factsheet, with the period preserved exactly (for example, 1 year, YTD, 3 years annualised, or since inception).
- Each row must include the factsheet/report date and the performance period end date where disclosed.
- Do not compare unlike periods without a clear label.
- If an underlying fund's own factsheet or return is unavailable, show **Not disclosed / not found** rather than estimate it.
- This version does not use daily exchange data as a substitute for factsheet performance.
""")
