import re
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

APP_TITLE = "NAV price"
AIA_DIRECTORY = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price"
AIA_HOME = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-SG,en;q=0.9",
}
REQUEST_TIMEOUT = 20

# Fallback catalogue: used only if AIA's directory does not expose all fund links
# in its HTML response. The app attempts to discover the full list from the live directory first.
FALLBACK_FUNDS = [
    ("AIA Acorns of Asia Fund", f"{AIA_DIRECTORY}/aia-acorns-of-asia-fund"),
    ("AIA Global Bond Fund", f"{AIA_DIRECTORY}/aia-global-bond-fund"),
    ("AIA Global Dynamic Income Fund", f"{AIA_DIRECTORY}/aia-global-dynamic-income-fund"),
    ("AIA Global Equity Fund", f"{AIA_DIRECTORY}/aia-global-equity-fund"),
    ("AIA Growth Fund", f"{AIA_DIRECTORY}/aia-growth-fund"),
    ("AIA Regional Fixed Income Fund", f"{AIA_DIRECTORY}/aia-regional-fixed-income-fund"),
    ("AIA US Equity Fund", f"{AIA_DIRECTORY}/aia-us-equity-fund"),
    ("AIA Sustainable Multi-Thematic Fund", f"{AIA_DIRECTORY}/aia-sustainable-multi-thematic-fund"),
    ("AIA Portfolio 50", f"{AIA_DIRECTORY}/aia-portfolio-50"),
    ("AIA Portfolio 100", f"{AIA_DIRECTORY}/aia-portfolio-100"),
    ("AIA Elite Balanced Fund (SGD)", f"{AIA_DIRECTORY}/aia-elite-balanced-fund-sgd"),
]

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1500px;}
    .hero {padding: 1.25rem 1.4rem; border-radius: 16px; border: 1px solid rgba(128,128,128,.28);
           background: linear-gradient(120deg, rgba(36,99,235,.10), rgba(14,165,233,.04));}
    .muted {opacity: .72; font-size: .9rem;}
    div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25); padding: .8rem; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero">
  <h1 style="margin:0">📈 {APP_TITLE}</h1>
  <p style="margin:.5rem 0 0 0">AIA Singapore ILP fund prices, daily NAV changes and disclosed underlying investments.</p>
  <p class="muted" style="margin:.4rem 0 0 0">Source-first monitor · Prices are published fund valuations, not live exchange quotes.</p>
</div>
""", unsafe_allow_html=True)

st.write("")

@st.cache_data(ttl=21600, show_spinner=False)
def get_html(url: str):
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def page_title(soup, fallback):
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" ", strip=True))
    if soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))
        return title.split("|")[0].strip()
    return fallback

@st.cache_data(ttl=21600, show_spinner=False)
def discover_funds():
    found = {}
    errors = []
    try:
        html = get_html(AIA_DIRECTORY)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = urljoin(AIA_DIRECTORY, a.get("href", ""))
            parsed = urlparse(href)
            path = parsed.path.rstrip("/")
            base_path = urlparse(AIA_DIRECTORY).path.rstrip("/")
            if path.startswith(base_path + "/"):
                slug = path[len(base_path) + 1:]
                if not slug or "/" in slug:
                    continue
                if any(x in slug.lower() for x in ["comparison", "fund-price", "page", "search"]):
                    continue
                label = clean_text(a.get_text(" ", strip=True))
                if not label or len(label) < 3:
                    label = slug.replace("-", " ").title()
                found[href] = (label, href)
    except Exception as exc:
        errors.append(str(exc))

    # Use fallback entries only for links not found in the directory response.
    for name, url in FALLBACK_FUNDS:
        found.setdefault(url, (name, url))

    funds = [{"name": name, "url": url} for name, url in found.values()]
    funds.sort(key=lambda x: x["name"].lower())
    return funds, errors

def extract_key_facts(soup):
    facts = {}
    # AIA fund pages usually present key facts in two-column tables.
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = clean_text(cells[0].get_text(" ", strip=True)).rstrip(":")
                value = clean_text(" ".join(c.get_text(" ", strip=True) for c in cells[1:]))
                if key and value and len(key) < 100:
                    facts[key] = value
    # Also inspect common semantic structures where content isn't a standard table.
    text = soup.get_text("\n", strip=True)
    labels = [
        "Investment objective", "Manager of ILP fund", "Manager of ILP Sub-Fund",
        "Annual management fee", "Source of fund", "Name of underlying fund",
        "Name of underlying funds", "Name of underlying funds", "Underlying investment",
        "Underlying Fund", "Benchmark", "Asset class", "Risk classification",
        "Fund currency", "Valuation date as of", "Bid price", "Offer price",
    ]
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    for i, line in enumerate(lines):
        for label in labels:
            if line.lower() == label.lower() and i + 1 < len(lines):
                facts.setdefault(label, lines[i + 1])
    return facts

def extract_documents(soup, page_url):
    docs = []
    for a in soup.select("a[href]"):
        label = clean_text(a.get_text(" ", strip=True))
        href = urljoin(page_url, a.get("href", ""))
        low = (label + " " + href).lower()
        if any(term in low for term in ["factsheet", "fund summary", "product highlights", ".pdf"]):
            if href.lower().endswith(".pdf") or any(term in low for term in ["factsheet", "fund summary", "product highlights"]):
                docs.append({"Document": label or "Fund document", "URL": href})
    unique = {}
    for doc in docs:
        unique[doc["URL"]] = doc
    return list(unique.values())

def parse_number(text):
    if not text:
        return None
    match = re.search(r"(?<!\w)(\d{1,6}(?:,\d{3})*(?:\.\d{2,6})?)(?!\w)", str(text))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None

def extract_prices(soup, facts):
    # Prefer explicit historical price tables, which allow the return to be calculated
    # from the two most recent available valuation dates.
    records = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [clean_text(x.get_text(" ", strip=True)).lower() for x in rows[0].find_all(["th", "td"])]
        date_idx = next((i for i, h in enumerate(header) if "date" in h), None)
        price_idx = next((i for i, h in enumerate(header) if "bid price" in h or h == "price" or "unit price" in h), None)
        if date_idx is None or price_idx is None:
            continue
        for row in rows[1:]:
            cells = [clean_text(x.get_text(" ", strip=True)) for x in row.find_all(["td", "th"])]
            if len(cells) <= max(date_idx, price_idx):
                continue
            date_text = cells[date_idx]
            price = parse_number(cells[price_idx])
            date = pd.to_datetime(date_text, dayfirst=True, errors="coerce")
            if pd.notna(date) and price is not None:
                records.append({"date": date.normalize(), "price": price})
    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["date"]).sort_values("date")
        return df

    # Some page templates render the latest bid price in text rather than a table.
    text = soup.get_text(" ", strip=True)
    price = None
    for key in ["Bid price", "Offer price"]:
        match = re.search(key + r"\s*(?:S\$|SGD|USD|\$)?\s*(\d+(?:\.\d{2,6})?)", text, re.I)
        if match:
            price = float(match.group(1))
            break
    if price is not None:
        date_text = facts.get("Valuation date as of", "")
        date = pd.to_datetime(date_text, dayfirst=True, errors="coerce")
        if pd.notna(date):
            return pd.DataFrame([{"date": date.normalize(), "price": price}])
    return pd.DataFrame(columns=["date", "price"])

@st.cache_data(ttl=21600, show_spinner=False)
def load_fund_page(url, fallback_name):
    try:
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        name = page_title(soup, fallback_name)
        facts = extract_key_facts(soup)
        prices = extract_prices(soup, facts)
        docs = extract_documents(soup, url)
        return {
            "name": name, "url": url, "facts": facts, "prices": prices,
            "documents": docs, "error": None,
        }
    except Exception as exc:
        return {
            "name": fallback_name, "url": url, "facts": {}, "prices": pd.DataFrame(columns=["date", "price"]),
            "documents": [], "error": str(exc),
        }

def price_summary(fund_data):
    prices = fund_data["prices"].sort_values("date")
    if prices.empty:
        return {
            "Fund": fund_data["name"], "Currency": fund_data["facts"].get("Fund currency", ""),
            "Latest price": None, "Previous price": None, "Change": None, "Return (%)": None,
            "Latest valuation date": "", "Previous valuation date": "",
            "Data status": "Price history not exposed in page HTML", "Fund page": fund_data["url"],
        }
    latest = prices.iloc[-1]
    previous = prices.iloc[-2] if len(prices) > 1 else None
    change = float(latest["price"] - previous["price"]) if previous is not None else None
    ret = (change / float(previous["price"]) * 100) if previous is not None and float(previous["price"]) != 0 else None
    return {
        "Fund": fund_data["name"], "Currency": fund_data["facts"].get("Fund currency", ""),
        "Latest price": float(latest["price"]),
        "Previous price": float(previous["price"]) if previous is not None else None,
        "Change": change, "Return (%)": ret,
        "Latest valuation date": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "Previous valuation date": pd.Timestamp(previous["date"]).strftime("%Y-%m-%d") if previous is not None else "",
        "Data status": "Calculated from published prices" if previous is not None else "Only one published price found",
        "Fund page": fund_data["url"],
    }

with st.sidebar:
    st.header("Settings")
    st.caption("Prices and fund facts are retrieved from AIA Singapore's public pages.")
    if st.button("🔄 Refresh official data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.markdown("**Official sources**")
    st.markdown(f"[AIA ILP Fund Prices]({AIA_DIRECTORY})")
    st.markdown(f"[AIA Fund Information]({AIA_HOME})")
    st.caption("AIA notes that fund prices are indicative and may not be updated in real time.")

funds, discovery_errors = discover_funds()
if not funds:
    st.error("Could not discover AIA fund pages. Check the official source link or try refreshing later.")
    st.stop()

tab_monitor, tab_holdings, tab_import, tab_sources = st.tabs(
    ["📊 NAV price monitor", "🧩 Fund details & holdings", "📤 Import price history", "ℹ️ Sources & methodology"]
)

with tab_monitor:
    st.subheader("All discovered AIA ILP funds")
    st.caption(f"{len(funds)} fund pages discovered or listed in the fallback catalogue. Availability may vary by policy.")
    query = st.text_input("Search funds", placeholder="Search by fund name, manager, or keyword")
    selected_names = st.multiselect("Filter by fund", options=[f["name"] for f in funds], default=[])
    if st.button("Load / update fund data", type="primary"):
        st.session_state["load_all"] = True

    load_all = st.session_state.get("load_all", False)
    if not load_all:
        st.info("Select **Load / update fund data** to retrieve the fund pages. This avoids sending many requests before you need them.")
    else:
        summaries = []
        fund_details = []
        progress = st.progress(0, text="Loading AIA fund pages…")
        for idx, fund in enumerate(funds):
            item = load_fund_page(fund["url"], fund["name"])
            fund_details.append(item)
            summaries.append(price_summary(item))
            progress.progress((idx + 1) / len(funds), text=f"Checking {idx + 1} of {len(funds)} funds")
        progress.empty()
        st.session_state["fund_details"] = fund_details
        df = pd.DataFrame(summaries)
        if query:
            df = df[df["Fund"].str.contains(query, case=False, na=False)]
        if selected_names:
            df = df[df["Fund"].isin(selected_names)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Funds listed", len(df))
        c2.metric("Funds with a calculable return", int(df["Return (%)"].notna().sum()))
        c3.metric("Fund pages with errors", sum(x["error"] is not None for x in fund_details))
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Latest price": st.column_config.NumberColumn(format="%.6f"),
                "Previous price": st.column_config.NumberColumn(format="%.6f"),
                "Change": st.column_config.NumberColumn(format="%+.6f"),
                "Return (%)": st.column_config.NumberColumn(format="%+.3f%%"),
                "Fund page": st.column_config.LinkColumn(display_text="Open AIA page"),
            },
        )
        st.download_button(
            "Download monitor as CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="nav_price_monitor.csv",
            mime="text/csv",
        )
        missing = df[df["Return (%)"].isna()]
        if not missing.empty:
            st.warning(
                "Some AIA pages load price history through dynamic components that may not appear in the HTML "
                "available to Streamlit. Those prices are left blank rather than estimated. Use the Import price "
                "history tab if you have a CSV of official historical prices."
            )

with tab_holdings:
    st.subheader("Fund details and disclosed underlying investments")
    if "fund_details" not in st.session_state:
        st.info("Load fund data in the NAV price monitor tab first.")
    else:
        details = st.session_state["fund_details"]
        names = [x["name"] for x in details]
        selected = st.selectbox("Choose a fund", names)
        item = next(x for x in details if x["name"] == selected)
        st.markdown(f"**Official fund page:** [{item['name']}]({item['url']})")
        if item["error"]:
            st.error(f"Could not retrieve this page: {item['error']}")
        facts = item["facts"]
        if facts:
            rows = [{"Field": k, "Value": v} for k, v in facts.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No key-facts table was detected in the page HTML. Open the official page below.")
        st.markdown("#### Fund documents")
        if item["documents"]:
            for doc in item["documents"]:
                st.markdown(f"- [{doc['Document']}]({doc['URL']})")
        else:
            st.caption("No document links were detected automatically.")
        st.markdown("#### Holdings coverage")
        st.write(
            "This section reports only underlying funds and holdings explicitly disclosed on AIA's public page. "
            "For look-through stock and bond holdings, open the linked factsheet or underlying fund report. "
            "AIA ILP funds may invest in other funds, so an ILP sub-fund's underlying fund name is not the same "
            "as a complete list of the stocks and bonds held by that underlying fund."
        )

with tab_import:
    st.subheader("Import official historical prices")
    st.write(
        "If AIA's interactive historical-price table is not included in the public page HTML, upload a CSV you "
        "downloaded or prepared from official AIA price records. The app calculates returns from consecutive "
        "available valuation dates; it does not fill missing prices."
    )
    st.markdown("**Required columns:** `fund_name`, `date`, `price`")
    sample = pd.DataFrame([
        {"fund_name": "Example Fund", "date": "2026-10-08", "price": 1.2345},
        {"fund_name": "Example Fund", "date": "2026-10-09", "price": 1.2400},
    ])
    st.download_button("Download CSV template", sample.to_csv(index=False).encode("utf-8"), "nav_price_template.csv", "text/csv")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded is not None:
        try:
            raw = pd.read_csv(uploaded)
            required = {"fund_name", "date", "price"}
            if not required.issubset(set(raw.columns)):
                st.error("CSV must contain these columns: fund_name, date, price.")
            else:
                raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
                raw["price"] = pd.to_numeric(raw["price"], errors="coerce")
                raw = raw.dropna(subset=["fund_name", "date", "price"]).sort_values(["fund_name", "date"])
                raw["previous_price"] = raw.groupby("fund_name")["price"].shift(1)
                raw["change"] = raw["price"] - raw["previous_price"]
                raw["return_pct"] = (raw["change"] / raw["previous_price"]) * 100
                st.dataframe(raw, use_container_width=True, hide_index=True)
                st.download_button("Download calculated returns", raw.to_csv(index=False).encode("utf-8-sig"),
                                   "nav_price_returns.csv", "text/csv")
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")

with tab_sources:
    st.subheader("Sources, definitions and limitations")
    st.markdown(f"- [AIA ILP Fund Prices]({AIA_DIRECTORY})")
    st.markdown(f"- [AIA Fund Information]({AIA_HOME})")
    st.markdown("- [AIA ILP Fund Tools](https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-ilp-fund-tools)")
    st.markdown("- [AIA Annual and Semi-Annual Fund Reports](https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-annual-funds-reports)")
    st.markdown("""
**Return calculation**

`Return (%) = (Latest price / Previous available price - 1) × 100`

- “Previous” means the prior available valuation date, which may not be the previous calendar day.
- Prices may be indicative and delayed. Fund NAVs are not live exchange prices.
- Currency and valuation dates should be checked before comparing funds.
- The funds shown on AIA's website may not all be available under every policy.
- The app does not invent missing prices. AIA's website may load prices through client-side services that cannot be read by a simple HTML request.
- Holdings are reported only to the level disclosed by AIA and its linked documents; complete security-level look-through is not always public.
""")
    if discovery_errors:
        st.warning("Directory request issue: " + " | ".join(discovery_errors))
    st.caption("This is an educational monitoring tool, not investment advice.")
