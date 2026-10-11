import re
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import urljoin, urlparse

import fitz
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_TITLE = "NAV price"
AIA_DIRECTORY = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price"
AIA_FUNDS_INFO = "https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information"
AIA_SITEMAPS = [
    "https://www.aia.com.sg/sitemap.xml",
    "https://www.aia.com.sg/en/sitemap.xml",
    "https://www.aia.com.sg/content/dam/sg-wise/sitemap.xml",
]
BASE_PATH = urlparse(AIA_DIRECTORY).path.rstrip("/")
TIMEOUT = (8, 15)

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1450px;padding-top:1.3rem}
.hero{padding:1.25rem 1.5rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;background:linear-gradient(120deg,rgba(220,38,38,.10),rgba(59,130,246,.06))}
.muted{opacity:.72;font-size:.9rem}
</style>
""", unsafe_allow_html=True)
st.markdown(f"""
<div class="hero"><h1 style="margin:0">📈 {APP_TITLE}</h1>
<p>AIA factsheet benchmark notes and reported performance</p>
<p class="muted">Finds official fund pages, locates factsheet PDFs, and extracts the document date, benchmark wording and reported returns.</p></div>
""", unsafe_allow_html=True)

@st.cache_resource
def get_session():
    s = requests.Session()
    retry = Retry(total=2, connect=2, read=1, backoff_factor=.5,
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

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def looks_like_fund_url(url):
    path = urlparse(url).path.rstrip("/")
    if not path.startswith(BASE_PATH + "/"):
        return False
    slug = path[len(BASE_PATH) + 1:]
    if not slug or "/" in slug:
        return False
    bad = ("comparison", "screener", "quickrank", "interactive-chart", "fund-performance", "fund-annual-performance")
    return not any(x in slug.lower() for x in bad)

def parse_fund_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.select("a[href]"):
        url = urljoin(base_url, a.get("href", ""))
        if looks_like_fund_url(url):
            path = urlparse(url).path.rstrip("/")
            slug = path.rsplit("/", 1)[-1]
            name = clean(a.get_text(" ", strip=True)) or slug.replace("-", " ").title()
            # Exclude generic navigation links with no plausible fund name.
            if len(slug) > 2:
                found[url] = {"name": name, "url": url, "catalogue_source": "AIA directory", "verified": True}
    return found

@st.cache_data(ttl=21600, show_spinner=False)
def discover_funds():
    errors = []
    found = {}
    # First attempt: official directory.
    try:
        found.update(parse_fund_links(get_html(AIA_DIRECTORY), AIA_DIRECTORY))
    except Exception as e:
        errors.append(f"Directory: {type(e).__name__}: {e}")
    # Second attempt: sitemap(s), useful when the interactive directory times out.
    if len(found) < 35:
        for sitemap_url in AIA_SITEMAPS:
            try:
                r = get_session().get(sitemap_url, timeout=TIMEOUT)
                if not r.ok or not r.text.lstrip().startswith("<"):
                    continue
                root = ET.fromstring(r.content)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                locs = [x.text for x in root.findall(".//sm:loc", ns) if x.text]
                # Follow sitemap indexes, but cap requests to avoid slow startup.
                if locs and all("sitemap" in x.lower() for x in locs[:5]):
                    candidate_locs = []
                    for child in locs[:20]:
                        try:
                            cr = get_session().get(child, timeout=TIMEOUT)
                            if cr.ok:
                                croot = ET.fromstring(cr.content)
                                candidate_locs.extend(x.text for x in croot.findall(".//sm:loc", ns) if x.text)
                        except Exception:
                            continue
                    locs = candidate_locs
                for url in locs:
                    if looks_like_fund_url(url):
                        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
                        found.setdefault(url, {"name": slug.replace("-", " ").title(), "url": url,
                                               "catalogue_source": "AIA sitemap", "verified": True})
                if len(found) >= 35:
                    break
            except Exception as e:
                errors.append(f"Sitemap: {type(e).__name__}: {e}")
    # A small seed list is intentionally not presented as the complete catalogue.
    if found:
        rows = sorted(found.values(), key=lambda x: x["name"].lower())
        return rows, ("Some fund pages may be missing; AIA returned only " + str(len(rows)) + " matching fund links.") if len(rows) < 35 else None, errors
    return [], "Could not retrieve the live directory or discover fund pages through AIA sitemaps. No unverified placeholder catalogue is shown.", errors

@st.cache_data(ttl=21600, show_spinner=False)
def page_documents(url):
    soup = BeautifulSoup(get_html(url), "html.parser")
    docs, seen = [], set()
    for a in soup.select("a[href]"):
        href = urljoin(url, a.get("href", ""))
        label = clean(a.get_text(" ", strip=True)) or "Fund document"
        low = (href + " " + label).lower()
        if (href.lower().split("?")[0].endswith(".pdf") or "factsheet" in low or "fund summary" in low) and href not in seen:
            seen.add(href)
            kind = "Factsheet" if "factsheet" in low else ("Fund summary" if "summary" in low else "PDF document")
            docs.append({"label": label, "kind": kind, "url": href})
    return docs

def download_pdf(url):
    r = get_session().get(url, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF-"):
        raise ValueError("The URL did not return a readable PDF file.")
    return r.content

def pdf_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [(i + 1, page.get_text("text", sort=True)) for i, page in enumerate(doc)]

def get_document_date(text):
    patterns = [r"(?:as of|as at|as on)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
                r"(?:prepared on|prepared as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
                r"(?:as of|as at|as on)\s+(\d{1,2}/\d{1,2}/\d{4})"]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", text, re.I)
    return f"{m.group(1)} {m.group(2)}" if m else "Not detected"

def extract_benchmark_notes(text):
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    out = []
    terms = ("current benchmark", "benchmark:", "benchmark^", "previous benchmark", "benchmark is", "benchmark changed")
    for i, line in enumerate(lines):
        if any(term in line.lower() for term in terms):
            chunk = [line]
            for nxt in lines[i + 1:i + 4]:
                if re.search(r"past performance|disclaimer|investments are subject", nxt, re.I):
                    break
                chunk.append(nxt)
            candidate = clean(" ".join(chunk))
            if candidate and candidate not in out:
                out.append(candidate)
    return out

def parse_performance_tables(text):
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    results, seen = [], set()
    percent_re = re.compile(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?\s*%")
    labels = ["Fund (bid-to-bid)", "Fund (bid to bid)", "Fund", "Benchmark", "Relative Return"]
    for i, line in enumerate(lines):
        if any(re.fullmatch(re.escape(label), line, re.I) for label in labels):
            nearby = " ".join(lines[i + 1:i + 6])
            vals = percent_re.findall(nearby)
            if vals:
                key = (line, tuple(vals))
                if key not in seen:
                    seen.add(key)
                    results.append({"Row candidate": line, "Extracted percentages": ", ".join(v.replace(" ", "") for v in vals), "Nearby PDF text": nearby[:600]})
    for line in lines:
        if any(x in line.lower() for x in ["fund (bid-to-bid)", "fund (bid to bid)", "benchmark", "relative return"]):
            vals = percent_re.findall(line)
            key = (line[:150], tuple(vals))
            if vals and key not in seen:
                seen.add(key)
                results.append({"Row candidate": line[:150], "Extracted percentages": ", ".join(v.replace(" ", "") for v in vals), "Nearby PDF text": line[:600]})
    return results

def parse_pdf(pdf_bytes):
    pages = pdf_text(pdf_bytes)
    text = "\n".join(t for _, t in pages)
    return {"pages": pages, "document_date": get_document_date(text), "benchmarks": extract_benchmark_notes(text),
            "performance": parse_performance_tables(text), "all_text": text}

def save_result(fund, doc, parsed):
    return {"Fund": fund, "Document type": doc.get("kind", "Uploaded PDF"), "Document date": parsed["document_date"],
            "Benchmark candidate": " | ".join(parsed["benchmarks"]) or "Not detected",
            "Performance candidates": " | ".join(x["Row candidate"] + ": " + x["Extracted percentages"] for x in parsed["performance"]) or "Not detected",
            "Source URL": doc.get("url", "")}

with st.sidebar:
    st.header("Data settings")
    if st.button("Refresh AIA catalogue and pages", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"[AIA fund-price directory]({AIA_DIRECTORY})")
    st.markdown(f"[AIA fund information]({AIA_FUNDS_INFO})")
    st.caption("Catalogue and document pages cached for 6 hours.")

st.info("This app extracts official factsheet wording and reported figures only. It does not estimate missing returns. Always verify extracted figures against the source PDF.")
funds, warning, errors = discover_funds()
if warning:
    st.warning(warning)
if errors:
    with st.expander("Directory discovery diagnostics"):
        for err in errors:
            st.write("- " + err)
st.caption(f"{len(funds)} fund pages discovered from AIA. This count reflects pages the app could identify, not a guarantee that every fund has a separate factsheet.")

if not funds:
    st.markdown(f"[Open the official AIA fund-price directory]({AIA_DIRECTORY})")
    st.write("You can still analyse an official factsheet using the upload tab below.")

tab_auto, tab_bulk, tab_upload, tab_method = st.tabs(["Find a factsheet", "Scan discovered funds", "Upload factsheet PDF", "Extraction notes"])
with tab_auto:
    if funds:
        search = st.text_input("Search AIA funds", placeholder="e.g. Acorns of Asia")
        filtered = [f for f in funds if search.lower() in f["name"].lower()] if search else funds
        if filtered:
            selected = st.selectbox("Choose fund", filtered, format_func=lambda f: f["name"])
            st.markdown(f"[Open official fund page]({selected['url']})")
            if st.button("Find official factsheet PDFs", type="primary"):
                try:
                    with st.spinner("Checking this fund page for official PDF links…"):
                        docs = page_documents(selected["url"])
                    st.session_state["doc_links"] = docs
                    st.session_state["doc_fund"] = selected["name"]
                except Exception as e:
                    st.error(f"Could not retrieve the fund page: {type(e).__name__}: {e}")
            if st.session_state.get("doc_fund") == selected["name"]:
                docs = st.session_state.get("doc_links", [])
                if docs:
                    st.markdown("#### Official documents found")
                    for d in docs:
                        st.markdown(f"- **{d['kind']}** — [{d['label']}]({d['url']})")
                    pdf_options = [d for d in docs if d["url"].lower().split("?")[0].endswith(".pdf")]
                    if pdf_options:
                        chosen = st.selectbox("Choose a PDF to analyse", pdf_options, format_func=lambda d: f"{d['kind']} — {d['url'].split('/')[-1]}")
                        if st.button("Extract benchmark and reported performance"):
                            try:
                                with st.spinner("Downloading and reading PDF…"):
                                    parsed = parse_pdf(download_pdf(chosen["url"]))
                                st.session_state["parsed_factsheet"] = parsed
                                st.session_state["parsed_source"] = chosen["url"]
                                st.session_state["parsed_fund"] = selected["name"]
                                st.session_state["parsed_kind"] = chosen["kind"]
                            except Exception as e:
                                st.error(f"Could not read the PDF: {type(e).__name__}: {e}")
                else:
                    st.warning("No PDF links were found on this page. Try the manual upload tab.")
    if "parsed_factsheet" in st.session_state:
        parsed = st.session_state["parsed_factsheet"]
        st.divider()
        st.subheader(f"Extraction result: {st.session_state.get('parsed_fund', 'Selected fund')}")
        st.write("**Document date:**", parsed["document_date"])
        st.write("**Source:**", st.session_state.get("parsed_source", ""))
        st.markdown("#### Benchmark wording candidates")
        if parsed["benchmarks"]:
            for b in parsed["benchmarks"]:
                st.write("- " + b)
        else:
            st.warning("No benchmark note was detected in the extracted PDF text.")
        st.markdown("#### Performance table candidates")
        if parsed["performance"]:
            st.dataframe(pd.DataFrame(parsed["performance"]), use_container_width=True, hide_index=True)
        else:
            st.warning("No likely performance rows were detected. This PDF may need a fund-specific parser or OCR.")
        with st.expander("Extracted PDF text (for checking)"):
            st.text(parsed["all_text"][:20000])

with tab_bulk:
    st.write("This checks every fund page discovered in the catalogue, finds linked PDF documents and attempts to extract factsheet data. It can take several minutes and some fund pages may fail or have no separate factsheet.")
    if funds and st.button("Scan all discovered funds", type="primary"):
        rows, failures = [], []
        progress = st.progress(0)
        status = st.empty()
        for idx, fund in enumerate(funds):
            status.write(f"Checking {idx + 1}/{len(funds)}: {fund['name']}")
            try:
                docs = page_documents(fund["url"])
                pdfs = [d for d in docs if d["url"].lower().split("?")[0].endswith(".pdf") and "factsheet" in (d["url"] + " " + d["label"]).lower()]
                if not pdfs:
                    rows.append({"Fund": fund["name"], "Status": "No factsheet PDF link detected", "Document date": "", "Benchmark": "", "Performance candidates": "", "Source URL": fund["url"]})
                else:
                    # Prefer the most recent-looking / explicitly labelled factsheet link.
                    chosen = sorted(pdfs, key=lambda d: ("factsheet" in d["label"].lower(), d["url"].lower()), reverse=True)[0]
                    parsed = parse_pdf(download_pdf(chosen["url"]))
                    rows.append({"Fund": fund["name"], "Status": "PDF parsed; verify figures", "Document date": parsed["document_date"],
                                 "Benchmark": " | ".join(parsed["benchmarks"]) or "Not detected",
                                 "Performance candidates": " | ".join(x["Row candidate"] + ": " + x["Extracted percentages"] for x in parsed["performance"]) or "Not detected",
                                 "Source URL": chosen["url"]})
            except Exception as e:
                rows.append({"Fund": fund["name"], "Status": f"Failed: {type(e).__name__}: {str(e)[:160]}", "Document date": "", "Benchmark": "", "Performance candidates": "", "Source URL": fund["url"]})
            progress.progress((idx + 1) / len(funds))
        st.session_state["bulk_rows"] = rows
        status.write("Scan finished.")
    if st.session_state.get("bulk_rows"):
        result_df = pd.DataFrame(st.session_state["bulk_rows"])
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        st.download_button("Download scan results as CSV", result_df.to_csv(index=False).encode("utf-8-sig"), "aia_factsheet_scan.csv", "text/csv")
        st.caption("‘PDF parsed’ means text extraction succeeded, not that every extracted value is guaranteed correct. Check the source PDF.")

with tab_upload:
    st.write("If AIA blocks automatic access, download the official factsheet from AIA and upload it here.")
    uploaded = st.file_uploader("Upload official factsheet PDF", type=["pdf"])
    source_url = st.text_input("Optional official PDF URL", placeholder="Paste the source URL so it can be recorded")
    fund_name = st.text_input("Fund name", placeholder="e.g. AIA Acorns of Asia Fund")
    if uploaded is not None and st.button("Extract uploaded factsheet", type="primary"):
        try:
            parsed = parse_pdf(uploaded.getvalue())
            st.session_state["parsed_factsheet"] = parsed
            st.session_state["parsed_source"] = source_url.strip() or uploaded.name
            st.session_state["parsed_fund"] = fund_name.strip() or uploaded.name
            st.session_state["parsed_kind"] = "Uploaded PDF"
            st.success("PDF text extraction completed.")
        except Exception as e:
            st.error(f"Could not read PDF: {type(e).__name__}: {e}")

with tab_method:
    st.markdown("""
**What this version does**
- Attempts the official fund-price directory first, then AIA sitemap discovery if the directory fails or returns too few fund pages.
- Lists only fund pages it actually discovers; it does not pretend a short fallback list is complete.
- Opens individual fund pages and searches for official factsheet PDF links.
- Extracts document-date candidates, benchmark wording and performance-table candidates from PDF text.
- Offers a bulk scan and CSV export for discovered fund pages.
- Allows manual PDF upload when automatic retrieval fails.

**Known limitations**
- AIA may render parts of the directory dynamically or block automated requests; a sitemap may not contain every fund page.
- PDF links can be image-only or dynamically loaded. Image-only PDFs need OCR, which is not included in this version.
- Performance rows are candidates, not a fully validated table-to-column mapping. Check the original factsheet before relying on figures.
- The latest factsheet is determined from the document link/page available at scan time; the app does not claim a PDF is current unless its reporting date is visible.
""")
