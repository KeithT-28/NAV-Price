import re, time
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import fitz
from bs4 import BeautifulSoup

st.set_page_config(page_title='NAV price — Investing.com test', page_icon='📈', layout='wide')
st.title('📈 NAV price — Investing.com daily data test')
st.write('Test whether Streamlit can retrieve daily MSCI benchmark history from Investing.com without a paid API or manual CSV upload.')
st.info('This is a source-access test. A successful download does not prove the series matches a fund’s exact benchmark variant. Do not use a proxy as an exact benchmark without verification.')

FACTSHEETS = [
    {'fund':'AIA US Equity Fund','url':'https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Sustainable Multi-Thematic Fund','url':'https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Shariah Global Diversified Fund','url':'https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA S$ Money Market Fund','url':'https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Regional Fixed Income Fund','url':'https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
]
INVESTING_URL = 'https://www.investing.com/indices/msci-world-net-usd-historical-data'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.investing.com/'
}


def parse_benchmark(text):
    # Search around all occurrences; terminate at effective-date metadata or a parenthetical note.
    candidates = []
    for m in re.finditer(r'current\s+benchmark\s*:\s*', text, re.I):
        tail = text[m.end():]
        # Most AIA notes put effective-date metadata in a parenthesis immediately after the name.
        cut_positions = []
        for pat in [r'\s*\(\s*w\.e\.f\.?', r'\s*\(\s*with effect', r'\s*\(\s*effective', r'\s*\(\d+\)', r'\s+previous benchmark\s*:', r'\s+there is an allocation']:
            mm = re.search(pat, tail, re.I)
            if mm: cut_positions.append(mm.start())
        end = min(cut_positions) if cut_positions else min(len(tail), 240)
        val = re.sub(r'\s+', ' ', tail[:end]).strip(' ;,:*')
        if val: candidates.append(val)
    return candidates[-1] if candidates else ''


def get_pdf_info(item):
    start = time.perf_counter()
    try:
        r = requests.get(item['url'], headers=HEADERS, timeout=(8, 25))
        elapsed = round(time.perf_counter() - start, 2)
        content_type = r.headers.get('Content-Type', '')
        if r.status_code != 200:
            return {'Fund':item['fund'],'PDF status':f'HTTP {r.status_code}','Seconds':elapsed,'PDF valid':False,'Factsheet date':'','Active benchmark':'','Source URL':item['url'],'Error':f'HTTP {r.status_code}; content-type={content_type}'}, ''
        doc = fitz.open(stream=r.content, filetype='pdf')
        text = '\n'.join(p.get_text('text') for p in doc)
        date_match = re.search(r'(?:as at|as of|factsheet as at|data as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', text, re.I)
        if not date_match:
            date_match = re.search(r'\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b', text)
        date = date_match.group(1) if date_match else ''
        bench = parse_benchmark(text)
        return {'Fund':item['fund'],'PDF status':'Downloaded','Seconds':elapsed,'PDF valid':True,'Factsheet date':date,'Active benchmark':bench or 'Current benchmark not detected','Source URL':item['url'],'Error':''}, text
    except Exception as e:
        return {'Fund':item['fund'],'PDF status':'Failed','Seconds':round(time.perf_counter()-start,2),'PDF valid':False,'Factsheet date':'','Active benchmark':'','Source URL':item['url'],'Error':str(e)[:250]}, ''


def fetch_investing():
    start = time.perf_counter()
    r = requests.get(INVESTING_URL, headers=HEADERS, timeout=(8, 25))
    elapsed = round(time.perf_counter()-start, 2)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}; {elapsed}s; content-type={r.headers.get("Content-Type", "unknown")}')
    soup = BeautifulSoup(r.text, 'html.parser')
    # Parse visible table rows rather than rely on pandas' implicit table detection.
    rows = []
    for tr in soup.select('table tbody tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.select('th,td')]
        if len(cells) >= 2:
            rows.append(cells)
    # Some page variants may render rows in divs; fail clearly rather than fabricate data.
    if not rows:
        title = soup.title.get_text(' ', strip=True) if soup.title else 'No title'
        raise RuntimeError(f'HTTP 200 but no visible historical table rows were found (page title: {title}). The site may render data dynamically or restrict automated access.')
    data=[]
    for cells in rows:
        date_text = cells[0]
        try:
            dt = pd.to_datetime(date_text, errors='raise')
        except Exception:
            continue
        # Investing.com historical table columns generally: Date, Price, Open, High, Low, Vol., Change %
        price = pd.to_numeric(cells[1].replace(',', ''), errors='coerce') if len(cells)>1 else None
        change = None
        if len(cells)>6:
            change = pd.to_numeric(cells[6].replace('%','').replace('+','').replace(',',''), errors='coerce')
        if pd.notna(price):
            data.append({'Date':dt.date().isoformat(),'Index level':float(price),'Daily return (%)':float(change) if pd.notna(change) else None})
    df = pd.DataFrame(data).drop_duplicates('Date').sort_values('Date', ascending=False)
    if df.empty:
        raise RuntimeError('The page loaded but no dated price rows could be parsed. HTML layout may have changed.')
    return df, elapsed, r.status_code, len(r.content), r.headers.get('Content-Type','')

if st.button('Fetch factsheets and test Investing.com', type='primary'):
    facts=[]; texts={}
    progress=st.progress(0)
    for i,item in enumerate(FACTSHEETS):
        row, txt = get_pdf_info(item); facts.append(row); texts[item['fund']]=txt
        progress.progress((i+1)/(len(FACTSHEETS)+1))
    st.subheader('Factsheet retrieval and benchmark extraction')
    fdf=pd.DataFrame(facts)
    st.dataframe(fdf[['Fund','PDF status','Seconds','PDF valid','Factsheet date','Active benchmark','Error']], use_container_width=True, hide_index=True)
    st.download_button('Download factsheet diagnostics CSV', fdf.to_csv(index=False).encode(), 'factsheet_diagnostics.csv', 'text/csv')
    with st.expander('Inspect extracted factsheet text'):
        for fund,txt in texts.items():
            st.markdown(f'**{fund}**')
            st.text_area(f'Source text — {fund}', txt[:12000] if txt else 'No text extracted.', height=140, key=f'text_{fund}')
    progress.progress(1.0)
    st.subheader('Investing.com: MSCI World Net USD daily history')
    st.caption('Test series: MSCI World Net USD (MIWO00000NUS). It is a candidate for testing data retrieval, not automatically an exact match for any fund benchmark.')
    try:
        df, secs, status, size, ctype = fetch_investing()
        st.success(f'Page retrieved: HTTP {status} · {secs}s · {size/1024:.1f} KB · {ctype}')
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)
        if len(df)>=2:
            a,b=df.iloc[0],df.iloc[1]
            st.markdown('#### Latest two available daily observations')
            out=pd.DataFrame([{'Series':'MSCI World Net USD (Investing.com)','T=0 date':a['Date'],'T=0 return (%)':a['Daily return (%)'],'T−1 date':b['Date'],'T−1 return (%)':b['Daily return (%)'],'Source':'Investing.com historical data'}])
            st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button('Download MSCI World daily history CSV', df.to_csv(index=False).encode(), 'investing_msc_world_net_usd.csv', 'text/csv')
        st.markdown(f'[Open source page]({INVESTING_URL})')
    except Exception as e:
        st.error(f'Investing.com retrieval failed: {e}')
        st.write('This indicates whether the source is accessible from Streamlit Cloud. It does not mean the data is unavailable in a normal browser.')
        st.markdown(f'[Open source page manually]({INVESTING_URL})')
    st.warning('Benchmark integrity: do not attach this series to a fund unless its factsheet benchmark exactly matches the series variant and currency. This test intentionally reports source data separately.')
else:
    st.markdown('### What this test does')
    st.markdown('- Downloads your five Morningstar factsheets.\n- Extracts factsheet dates and candidate “Current benchmark” text.\n- Attempts to retrieve daily history for **MSCI World Net USD** from Investing.com without a manual CSV or API key.\n- Shows the latest two available daily returns and a diagnostics CSV if the page is accessible.')
    st.markdown(f'Source under test: [{INVESTING_URL}]({INVESTING_URL})')
