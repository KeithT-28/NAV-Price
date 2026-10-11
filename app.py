import re
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_TITLE = "NAV price"
AIA_DIRECTORY = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price"
AIA_FUNDS = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information"
TIMEOUT = (8, 18)  # connect timeout, response timeout

# Fallback is deliberately labelled as a starter list. AIA's full live directory
# should be verified against the official page when it becomes reachable.
FALLBACK_FUNDS = [
    "AIA Acorns of Asia Fund",
    "AIA Diversified Fixed Income Fund",
    "AIA Equity Income Fund",
    "AIA Global Corporate Bond Fund",
    "AIA Global Dynamic Income Fund",
    "AIA Global Equity Fund",
    "AIA Global Bond Fund",
    "AIA Growth Fund",
    "AIA Regional Fixed Income Fund",
    "AIA US Equity Fund",
    "AIA US High Yield Bond Fund",
]

@st.cache_resource
def session():
    s = requests.Session()
    retry = Retry(total=2, connect=2, read=1, backoff_factor=0.7,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-SG,en;q=0.9",
    })
    return s

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
def fetch_html(url):
    response = session().get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

@st.cache_data(ttl=21600, show_spinner=False)
def discover_funds():
    """Try AIA live directory; never make app startup depend on this request."""
    try:
        html = fetch_html(AIA_DIRECTORY)
        soup = BeautifulSoup(html, "html.parser")
        found = {}
        base_path = urlparse(AIA_DIRECTORY).path.rstrip("/")
        for a in soup.select("a[href]"):
            url = urljoin(AIA_DIRECTORY, a.get("href", ""))
            path = urlparse(url).path.rstrip("/")
            if path.startswith(base_path + "/"):
                slug = path[len(base_path) + 1:]
                if not slug or "/" in slug or any(x in slug.lower() for x in ["comparison", "screener", "quickrank"]):
                    continue
                name = clean(a.get_text(" ", strip=True)) or slug.replace("-", " ").title()
                found[url] = {"name": name, "url": url, "source": "Discovered from AIA directory"}
        if found:
            return sorted(found.values(), key=lambda x: x["name"].lower()), None
        return fallback_funds(), "AIA responded, but fund links were not found in the returned HTML."
    except Exception as exc:
        return fallback_funds(), f"AIA's directory could not be reached: {exc}"

def fallback_funds():
    return [{"name": name, "url": AIA_DIRECTORY, "source": "Fallback list — verify on official AIA directory"}
            for name in FALLBACK_FUNDS]

def extract_facts(soup):
    facts = {}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if len(cells) >= 2 and cells[0] and " ".join(cells[1:]):
                facts[cells[0].rstrip(":")] = " | ".join(cells[1:])
    lines = [clean(x) for x in soup.get_text("\n").splitlines() if clean(x)]
    labels = ["Investment objective", "Benchmark", "Underlying Funds", "Underlying fund",
              "Fund currency", "Manager of ILP fund", "Valuation date as of"]
    for i, line in enumerate(lines[:-1]):
        if any(line.lower() == label.lower() for label in labels):
            facts.setdefault(line, lines[i+1])
    return facts

def document_links(soup, page_url):
    output, seen = [], set()
    for a in soup.select("a[href]"):
        href = urljoin(page_url, a.get("href", ""))
        label = clean(a.get_text(" ", strip=True)) or "Fund document"
        test = (label + " " + href).lower()
        if (href.lower().endswith(".pdf") or "factsheet" in test or "fund summary" in test) and href not in seen:
            seen.add(href)
            output.append({"Document": label, "URL": href})
    return output

@st.cache_data(ttl=21600, show_spinner=False)
def load_selected_fund(url, name):
    try:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        facts = extract_facts(soup)
        docs = document_links(soup, url)
        return {"facts": facts, "docs": docs, "error": None}
    except Exception as exc:
        return {"facts": {}, "docs": [], "error": str(exc)}

with st.sidebar:
    st.header("Data settings")
    if st.button("Refresh AIA pages", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"[AIA fund-price directory]({AIA_DIRECTORY})")
    st.markdown(f"[AIA fund information]({AIA_FUNDS})")
    st.caption("Successful page results are cached for up to 6 hours.")

funds, discovery_warning = discover_funds()
st.info("This version prioritises the latest official factsheet's reported performance and underlying funds only. It does not substitute live market returns for factsheet returns.")
if discovery_warning:
    st.warning(
        discovery_warning + "\n\nThe app has opened using a fallback fund list instead of stopping. "
        "The fallback list is not guaranteed to be complete; verify availability and fund names on AIA's official directory."
    )

st.subheader("Choose an AIA ILP fund")
search = st.text_input("Search funds", placeholder="e.g. Global Dynamic Income")
filtered = [f for f in funds if search.lower() in f["name"].lower()] if search else funds
if not filtered:
    st.warning("No matching fund. Clear the search or refresh AIA pages.")
    st.stop()

chosen = st.selectbox("Fund", filtered, format_func=lambda f: f["name"])
st.caption(chosen["source"])
if st.button("Load selected fund details", type="primary"):
    st.session_state["fund_details"] = load_selected_fund(chosen["url"], chosen["name"])
    st.session_state["selected_fund_name"] = chosen["name"]

data = st.session_state.get("fund_details")
if data:
    st.divider()
    st.subheader(st.session_state.get("selected_fund_name", chosen["name"]))
    if data["error"]:
        st.error(f"Could not retrieve this page: {data['error']}")
    if chosen["url"] == AIA_DIRECTORY:
        st.warning("This entry came from the fallback list. The app has not verified a dedicated page for this fund yet.")
        st.markdown(f"Open the official AIA directory and select the fund: [AIA ILP fund prices]({AIA_DIRECTORY})")
    if data["facts"]:
        st.markdown("### Fund facts")
        st.dataframe(pd.DataFrame([{"Field": k, "Value": v} for k,v in data["facts"].items()]),
                     use_container_width=True, hide_index=True)
    if data["docs"]:
        st.markdown("### Official documents detected")
        st.dataframe(pd.DataFrame(data["docs"]), use_container_width=True, hide_index=True,
                     column_config={"URL": st.column_config.LinkColumn()})
    else:
        st.info("No factsheet links were detected automatically. Open the official AIA directory and choose the fund to locate its latest factsheet.")

st.divider()
with st.expander("How NAV price handles data"):
    st.markdown("""
- Factsheet return means the performance figure printed in the latest official factsheet.
- Each return must retain its stated period and factsheet/report date.
- The parent ILP fund's return is not the same as the return of an underlying fund.
- If the underlying fund's own factsheet does not disclose a return, the app should show **Not disclosed / not found**.
- The fallback list is a resilience measure, not a claim that the list contains every currently available AIA ILP fund.
""")
