import re
import time
from io import BytesIO
from datetime import datetime

import fitz
import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_TITLE = "NAV price — Five Factsheet Link Test"
TIMEOUT = (8, 25)  # connect timeout, response/read timeout
LINKS = [
    (1, "AIA US Equity Fund", "https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"),
    (2, "AIA Sustainable Multi-Thematic Fund", "https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"),
    (3, "AIA Shariah Global Diversified Fund", "https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"),
    (4, "AIA S$ Money Market Fund", "https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"),
    (5, "AIA Regional Fixed Income Fund", "https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"),
]

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
st.title("📈 NAV price — Five Factsheet Link Test")
st.write("Test these five direct Morningstar factsheet links from the **Streamlit hosting environment**. The app reports download status, response time, PDF validity, document date, benchmark candidates and performance-table text.")
st.info("This test uses direct PDF links rather than AIA's fund directory. It does not assume that a successful download means the extracted benchmark is correct; inspect the source text before relying on the result.")

@st.cache_resource
def session():
    s = requests.Session()
    retry = Retry(total=1, connect=1, read=0, backoff_factor=0.3,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"],
                  raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; NAVPriceFactsheetTester/1.0)"})
    return s

def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()

def extract_candidates(text):
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    # Keep context around benchmark labels; do not pretend a single line always contains the full benchmark.
    bench = []
    for i, line in enumerate(lines):
        if re.search(r"benchmark|reference index|comparative index", line, re.I):
            start, end = max(0, i-1), min(len(lines), i+3)
            candidate = " | ".join(lines[start:end])
            if candidate not in bench:
                bench.append(candidate)
    date_patterns = [
        r"(?:as at|as of|data as at|factsheet as at|valuation date)\s*[:\-]?\s*([A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
    ]
    dates = []
    for pat in date_patterns:
        for m in re.finditer(pat, text, re.I):
            val = norm(m.group(1) if m.lastindex else m.group(0))
            if val not in dates:
                dates.append(val)
    perf = []
    for i, line in enumerate(lines):
        if re.search(r"performance|cumulative returns|annualised returns|annualized returns|1 month|1 m\b|since inception", line, re.I):
            snippet = " | ".join(lines[i:min(len(lines), i+9)])
            if snippet not in perf:
                perf.append(snippet)
            if len(perf) >= 8:
                break
    return lines, bench[:12], dates[:12], perf

def test_link(number, name, url):
    started = time.perf_counter()
    try:
        response = session().get(url, timeout=TIMEOUT, allow_redirects=True)
        elapsed = round(time.perf_counter() - started, 2)
        content_type = response.headers.get("Content-Type", "")
        body = response.content or b""
        if response.status_code != 200:
            return {"No.": number, "Fund (label)": name, "Status": "HTTP error", "HTTP": response.status_code, "Seconds": elapsed, "Size (KB)": round(len(body)/1024, 1), "Content-Type": content_type, "PDF valid": False, "Reporting date candidates": "", "Benchmark candidates": "", "Performance candidates": "", "Text": f"HTTP {response.status_code}: {response.text[:500]}"}
        if not body.startswith(b"%PDF"):
            return {"No.": number, "Fund (label)": name, "Status": "Not a PDF", "HTTP": response.status_code, "Seconds": elapsed, "Size (KB)": round(len(body)/1024, 1), "Content-Type": content_type, "PDF valid": False, "Reporting date candidates": "", "Benchmark candidates": "", "Performance candidates": "", "Text": body[:500].decode("utf-8", "replace")}
        doc = fitz.open(stream=body, filetype="pdf")
        page_count = len(doc)
        text = "\n".join(page.get_text("text") for page in doc)
        doc.close()
        lines, bench, dates, perf = extract_candidates(text)
        status = "Downloaded; text found" if len(text.strip()) > 80 else "PDF downloaded; little/no selectable text"
        return {"No.": number, "Fund (label)": name, "Status": status, "HTTP": response.status_code, "Seconds": elapsed, "Size (KB)": round(len(body)/1024, 1), "Content-Type": content_type, "PDF valid": True, "Pages": page_count, "Reporting date candidates": "\n---\n".join(dates), "Benchmark candidates": "\n---\n".join(bench), "Performance candidates": "\n---\n".join(perf), "Text": text[:16000]}
    except requests.exceptions.Timeout as e:
        return {"No.": number, "Fund (label)": name, "Status": "Timeout", "HTTP": "", "Seconds": round(time.perf_counter()-started, 2), "Size (KB)": 0, "Content-Type": "", "PDF valid": False, "Reporting date candidates": "", "Benchmark candidates": "", "Performance candidates": "", "Text": str(e)}
    except Exception as e:
        return {"No.": number, "Fund (label)": name, "Status": "Error", "HTTP": "", "Seconds": round(time.perf_counter()-started, 2), "Size (KB)": 0, "Content-Type": "", "PDF valid": False, "Reporting date candidates": "", "Benchmark candidates": "", "Performance candidates": "", "Text": f"{type(e).__name__}: {e}"}

with st.expander("Five test URLs", expanded=False):
    for n, name, url in LINKS:
        st.markdown(f"**{n}. {name}**  \n[{url}]({url})")

if st.button("Run test on all 5 links", type="primary"):
    results = []
    progress = st.progress(0)
    status_area = st.empty()
    for i, (number, name, url) in enumerate(LINKS, start=1):
        status_area.write(f"Testing link {number}/5: {name}…")
        results.append(test_link(number, name, url))
        progress.progress(i/len(LINKS))
    st.session_state["link_results"] = results
    status_area.success("Test finished.")

if "link_results" in st.session_state:
    results = st.session_state["link_results"]
    df = pd.DataFrame([{k: r.get(k, "") for k in ["No.", "Fund (label)", "Status", "HTTP", "Seconds", "Size (KB)", "Content-Type", "PDF valid", "Pages"]} for r in results])
    st.subheader("Download results")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download diagnostic CSV", pd.DataFrame(results).drop(columns=["Text"], errors="ignore").to_csv(index=False).encode("utf-8"), file_name="nav_price_five_link_test.csv", mime="text/csv")
    for r in results:
        with st.expander(f"Link {r['No.']}: {r['Fund (label)']} — {r['Status']}", expanded=(r['Status'] != "Downloaded; text found")):
            c1, c2, c3 = st.columns(3)
            c1.metric("HTTP status", str(r.get("HTTP", "—")))
            c2.metric("Download time", f"{r.get('Seconds', 0)} s")
            c3.metric("PDF size", f"{r.get('Size (KB)', 0)} KB")
            st.write("**Reporting date candidates**")
            st.text(r.get("Reporting date candidates") or "No date candidate detected")
            st.write("**Benchmark candidates**")
            st.text(r.get("Benchmark candidates") or "No benchmark candidate detected")
            st.write("**Performance table candidates**")
            st.text(r.get("Performance candidates") or "No performance candidate detected")
            with st.expander("Extracted PDF text (first 16,000 characters)"):
                st.text(r.get("Text", ""))
else:
    st.caption("No links tested yet. Press the button above to test all five from the deployed app.")

st.caption(f"Per-request timeout: {TIMEOUT[0]} seconds to connect, {TIMEOUT[1]} seconds to receive data. One limited retry is configured for selected server errors. Total test time can exceed a single timeout because five URLs are checked sequentially.")
