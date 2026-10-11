import re
from io import BytesIO
from urllib.parse import urljoin, urlparse

import fitz  # PyMuPDF
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_TITLE = "NAV price"
AIA_DIRECTORY = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price"
AIA_FUNDS_INFO = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information"
TIMEOUT = (8, 20)

FALLBACK_FUNDS = [
    "AIA Acorns of Asia Fund", "AIA Asia Pacific Equity Fund", "AIA Balanced Fund",
    "AIA Diversified Fixed Income Fund", "AIA Equity Income Fund", "AIA Global Bond Fund",
    "AIA Global Corporate Bond Fund", "AIA Global Dynamic Income Fund", "AIA Global Equity Fund",
    "AIA Global Technology Fund", "AIA Growth Fund", "AIA Regional Fixed Income Fund",
    "AIA US Equity Fund", "AIA US High Yield Bond Fund",
]

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1450px;padding-top:1.3rem}
.hero{padding:1.25rem 1.5rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;background:linear-gradient(120deg,rgba(220,38,38,.10),rgba(59,130,246,.06))}
.muted{opacity:.72;font-size:.9rem}
</style>
""", unsafe_allow_html=True)
st.markdown(f"""
<div class="hero">
<h1 style="margin:0">📈 {APP_TITLE}</h1>
<p>AIA factsheet benchmark notes and reported performance</p>
<p class="muted">Extracts the benchmark wording and performance figures from an official factsheet PDF. Reports the document date and source.</p>
</div>
""", unsafe_allow_html=True)

@st.cache_resource
def get_session():
    s = requests.Session()
    retry = Retry(total=2, connect=2, read=1, backoff_factor=.6,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})
    return s

@st.cache_data(ttl=21600, show_spinner=False)
def get_html(url):
    r = get_session().get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

@st.cache_data(ttl=21600, show_spinner=False)
def discover_funds():
    try:
        soup = BeautifulSoup(get_html(AIA_DIRECTORY), "html.parser")
        found = {}
        base_path = urlparse(AIA_DIRECTORY).path.rstrip("/")
        for a in soup.select("a[href]"):
            url = urljoin(AIA_DIRECTORY, a.get("href", ""))
            path = urlparse(url).path.rstrip("/")
            if path.startswith(base_path + "/"):
                slug = path[len(base_path)+1:]
                if not slug or "/" in slug or any(x in slug.lower() for x in ["comparison", "screener", "quickrank"]):
                    continue
                name = " ".join(a.get_text(" ", strip=True).split()) or slug.replace("-", " ").title()
                found[url] = {"name": name, "url": url, "verified": True}
        if found:
            return sorted(found.values(), key=lambda x: x["name"].lower()), None
        return fallback(), "AIA responded but no fund links were detected. Showing an unverified fallback list."
    except Exception as e:
        return fallback(), f"Live AIA directory unavailable ({e}). Showing an unverified fallback list."

def fallback():
    return [{"name": n, "url": AIA_DIRECTORY, "verified": False} for n in FALLBACK_FUNDS]

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

@st.cache_data(ttl=21600, show_spinner=False)
def page_documents(url):
    if url == AIA_DIRECTORY:
        return []
    soup = BeautifulSoup(get_html(url), "html.parser")
    docs = []
    seen = set()
    for a in soup.select("a[href]"):
        href = urljoin(url, a.get("href", ""))
        label = clean(a.get_text(" ", strip=True)) or "Fund document"
        low = (href + " " + label).lower()
        if (href.lower().endswith(".pdf") or "factsheet" in low or "fund summary" in low) and href not in seen:
            seen.add(href)
            docs.append({"label": label, "url": href})
    return docs

def download_pdf(url):
    response = get_session().get(url, timeout=TIMEOUT)
    response.raise_for_status()
    if "pdf" not in response.headers.get("content-type", "").lower() and not url.lower().endswith(".pdf"):
        # Try parsing anyway, but reject obvious HTML.
        if response.content[:5] != b"%PDF-":
            raise ValueError("The link did not return a PDF file.")
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("The selected URL does not appear to be a PDF.")
    return response.content

def pdf_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        pages.append((i + 1, page.get_text("text", sort=True)))
    return pages

def get_document_date(text):
    patterns = [
        r"(?:as of|as at|as on)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"(?:prepared on|prepared as at|factsheet\s*[:|]?\s*)(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"(?:as of|as at|as on)\s+(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", text, re.I)
    return f"{m.group(1)} {m.group(2)}" if m else "Not detected"

def extract_benchmark_notes(text):
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    out = []
    terms = ("current benchmark", "benchmark:", "benchmark^", "previous benchmark", "combined benchmark")
    for i, line in enumerate(lines):
        if any(term in line.lower() for term in terms):
            # Keep the actual note and a few following lines to capture wrapped PDF text.
            chunk = [line]
            for nxt in lines[i+1:i+4]:
                if re.search(r"past performance|disclaimer|investments are subject|notes?\s*\(", nxt, re.I):
                    break
                chunk.append(nxt)
            candidate = clean(" ".join(chunk))
            if candidate and candidate not in out:
                out.append(candidate)
    return out

def parse_performance_tables(text):
    """Conservative parser: extracts text rows only when a row label and percentages are nearby."""
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    results = []
    periods = ["1 Month", "3 Months", "6 Months", "YTD", "1 Year", "3 Year", "5 Year", "10 Year", "Since Inception"]
    percent_re = re.compile(r"[-+]?\d{1,3}(?:\.\d{1,4})?\s*%")
    labels = ["Fund (bid-to-bid)", "Fund (bid to bid)", "Fund", "Benchmark", "Relative Return", "Class I", "Class A", "Class"]
    for i, line in enumerate(lines):
        if any(re.fullmatch(re.escape(label), line, re.I) for label in labels):
            nearby = " ".join(lines[i+1:i+5])
            vals = percent_re.findall(nearby)
            if vals:
                results.append({"Row": line, "Extracted percentages": ", ".join(v.replace(" ", "") for v in vals),
                                "Text around row": nearby[:500]})
    # Capture rows where all values are on same line.
    for line in lines:
        low = line.lower()
        if any(label.lower() in low for label in ["fund (bid-to-bid)", "fund (bid to bid)", "benchmark", "relative return", "annualized returns", "cumulative returns"]):
            vals = percent_re.findall(line)
            if vals:
                item = {"Row": line[:100], "Extracted percentages": ", ".join(v.replace(" ", "") for v in vals),
                        "Text around row": line[:500]}
                if item not in results:
                    results.append(item)
    return results

def parse_pdf(pdf_bytes):
    pages = pdf_text(pdf_bytes)
    all_text = "\n".join(t for _, t in pages)
    return {
        "pages": pages,
        "document_date": get_document_date(all_text),
        "benchmarks": extract_benchmark_notes(all_text),
        "performance": parse_performance_tables(all_text),
        "all_text": all_text,
    }

with st.sidebar:
    st.header("Data settings")
    if st.button("Refresh AIA pages", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"[AIA fund-price directory]({AIA_DIRECTORY})")
    st.markdown(f"[AIA fund information]({AIA_FUNDS_INFO})")
    st.caption("Directory/document pages cached for up to 6 hours.")

st.write("This version extracts the highlighted benchmark note and the reported performance table from a factsheet PDF. It does not estimate missing values. Since PDF layouts differ, extracted figures should be checked against the source PDF.")

funds, warning = discover_funds()
if warning:
    st.warning(warning + " The fallback catalogue may not be complete.")
st.caption(f"{len(funds)} fund entries available in the selector. Verify that the selected fund is available under your policy.")

tab_auto, tab_upload, tab_method = st.tabs(["Find AIA factsheet", "Upload factsheet PDF", "Extraction notes"])

with tab_auto:
    search = st.text_input("Search AIA funds", placeholder="e.g. Acorns of Asia")
    filtered = [f for f in funds if search.lower() in f["name"].lower()] if search else funds
    if filtered:
        selected = st.selectbox("Choose fund", filtered, format_func=lambda f: f["name"])
        if not selected["verified"]:
            st.info("This is a fallback entry; the app has not verified a dedicated fund page because the live directory was unavailable.")
            st.markdown(f"[Open AIA fund-price directory]({AIA_DIRECTORY})")
        else:
            if st.button("Find official factsheet links", type="primary"):
                try:
                    with st.spinner("Checking this fund page for factsheet and summary PDF links…"):
                        docs = page_documents(selected["url"])
                    st.session_state["doc_links"] = docs
                    st.session_state["doc_fund"] = selected["name"]
                except Exception as e:
                    st.error(f"Could not retrieve the selected fund page: {e}")
        if st.session_state.get("doc_fund") == selected["name"]:
            docs = st.session_state.get("doc_links", [])
            if docs:
                st.markdown("#### Documents found")
                for i, d in enumerate(docs):
                    st.markdown(f"- [{d['label']}]({d['url']})")
                options = [d for d in docs if d["url"].lower().endswith(".pdf")]
                if options:
                    chosen_doc = st.selectbox("Choose PDF to analyse", options, format_func=lambda d: d["label"] + " — " + d["url"].split("/")[-1])
                    if st.button("Extract benchmark and performance"):
                        try:
                            with st.spinner("Downloading and reading the PDF…"):
                                parsed = parse_pdf(download_pdf(chosen_doc["url"]))
                            st.session_state["parsed_factsheet"] = parsed
                            st.session_state["parsed_source"] = chosen_doc["url"]
                            st.session_state["parsed_fund"] = selected["name"]
                        except Exception as e:
                            st.error(f"Could not extract this PDF: {e}")
            else:
                st.info("No PDF links were detected on the page. Upload the latest factsheet in the next tab, or open the official AIA page to download it manually.")

with tab_upload:
    st.write("Use this if AIA's site blocks automatic access or if you already downloaded the latest factsheet. The PDF stays in this app session; the app extracts text locally.")
    uploaded = st.file_uploader("Upload official AIA factsheet PDF", type=["pdf"])
    source_url = st.text_input("Optional official PDF URL", placeholder="Paste the source URL so it can be recorded")
    if uploaded is not None and st.button("Extract uploaded factsheet", type="primary"):
        try:
            with st.spinner("Reading PDF text…"):
                parsed = parse_pdf(uploaded.getvalue())
            st.session_state["parsed_factsheet"] = parsed
            st.session_state["parsed_source"] = source_url.strip() or uploaded.name
            st.session_state["parsed_fund"] = uploaded.name
        except Exception as e:
            st.error(f"Could not read PDF: {e}")

with tab_method:
    st.markdown("""
**Fields extracted**
- Factsheet/reporting date (when detectable).
- Current benchmark notes and benchmark-change history, including index names, weights and effective dates when present.
- Performance rows such as Fund (bid-to-bid), Benchmark, Relative Return, and percentage values printed in the PDF.

**Accuracy rules**
- The extracted figures are not automatically assigned to period columns unless the PDF text structure makes that mapping unambiguous.
- A PDF may have text embedded as an image; this extractor will then need OCR.
- The benchmark note identifies what the fund is measured against. It does not necessarily list underlying investable funds.
- If an AIA page or PDF is unavailable, no figures are fabricated.
""")

parsed = st.session_state.get("parsed_factsheet")
if parsed:
    st.divider()
    st.subheader("Factsheet extraction results")
    st.write(f"**Fund / file:** {st.session_state.get('parsed_fund', 'Factsheet')}")
    st.write(f"**Factsheet date detected:** {parsed['document_date']}")
    st.write(f"**Source:** {st.session_state.get('parsed_source', 'Not supplied')}")
    st.markdown("### Benchmark notes")
    if parsed["benchmarks"]:
        for note in parsed["benchmarks"]:
            st.write("• " + note)
    else:
        st.info("No benchmark note was detected automatically. Check the extracted text below or the source PDF.")
    st.markdown("### Performance rows detected")
    if parsed["performance"]:
        st.dataframe(pd.DataFrame(parsed["performance"]), use_container_width=True, hide_index=True)
        st.caption("These are candidate text extractions. Verify the values and period headings against the PDF before relying on them.")
        csv = pd.DataFrame(parsed["performance"]).to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download extracted performance rows", csv, "nav_price_factsheet_extract.csv", "text/csv")
    else:
        st.info("No performance rows were confidently detected in the PDF text. It may require OCR or a fund-specific parser.")
    with st.expander("Inspect extracted PDF text"):
        st.text_area("PDF text", parsed["all_text"][:30000], height=450)
