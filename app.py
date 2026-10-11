import re
import pandas as pd
import requests
import streamlit as st
import fitz
import yfinance as yf

st.set_page_config(page_title='NAV price | Daily Benchmark Monitor', page_icon='📈', layout='wide')
KEY = 'fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'
FUNDS = [
    {'fund':'AIA US Equity Fund','url':f'https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key={KEY}', 'ticker':'^SP500TR', 'source_name':'S&P 500 Total Return Index', 'match':'Approximation only: factsheet says S&P 500 Net Total Return; Yahoo series is labelled S&P 500 Total Return. Do not treat as exact.', 'source':'Yahoo Finance'},
    {'fund':'AIA Sustainable Multi-Thematic Fund','url':f'https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key={KEY}', 'ticker':'^990100-USD-STRD', 'source_name':'MSCI World (USD series)', 'match':'Candidate series. Confirm the factsheet currency and net/gross return variant before treating as exact.', 'source':'Yahoo Finance'},
    {'fund':'AIA Shariah Global Diversified Fund','url':f'https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key={KEY}', 'ticker':None, 'source_name':'Composite benchmark', 'match':'Not automatically calculated: benchmark is blended; exact component series and official weighting/rebalancing methodology need verification.', 'source':'Provider series required'},
    {'fund':'AIA S$ Money Market Fund','url':f'https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key={KEY}', 'ticker':None, 'source_name':'SGD 1-month deposit rate', 'match':'Rate benchmark rather than a conventional daily index-level series; daily return may not be meaningful.', 'source':'Official rate source required'},
    {'fund':'AIA Regional Fixed Income Fund','url':f'https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key={KEY}', 'ticker':None, 'source_name':'Markit iBoxx SGD Overall Index TR', 'match':'Exact daily total-return series not yet verified as freely available.', 'source':'iBoxx / index provider required'},
]
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; NAVPriceResearch/1.0)'}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pdf(url):
    r = requests.get(url, headers=HEADERS, timeout=(8, 25))
    r.raise_for_status()
    if r.content[:4] != b'%PDF' and 'pdf' not in r.headers.get('Content-Type','').lower():
        raise ValueError(f"Response is not a PDF (Content-Type: {r.headers.get('Content-Type','unknown')})")
    doc = fitz.open(stream=r.content, filetype='pdf')
    text = '\n'.join(p.get_text('text') for p in doc)
    return text, len(r.content), len(doc)

def clean_pdf_text(text):
    """Normalize whitespace while preserving enough punctuation for benchmark parsing."""
    return re.sub(r'\s+', ' ', text).strip()


def extract_current_benchmark(text):
    """Extract the current benchmark clause, excluding effective-date/footnote metadata.

    The source PDFs often place '(w.e.f. ...)' immediately after the benchmark name.
    For composite benchmarks, retain the full component wording and weights.
    """
    normalized = clean_pdf_text(text)
    patterns = [
        r'Current\s+benchmark\s*:\s*(.+?)(?=\s*\(\s*w\.?\s*e\.?\s*f\.?\b|\s*\(\s*with\s+effect\b|\s*\(\s*effective\b|\s*\(\s*previous\s+benchmark\b|\s*\(\s*\d+\s*\)|\s*Disclaimer\b|$)',
        r'Current\s+benchmark\s*:\s*(.+?)(?=\s+Previous\s+benchmark\s*:|\s+Past\s+performance\b|\s+The\s+benchmark\b|$)',
    ]
    for pat in patterns:
        m = re.search(pat, normalized, flags=re.I)
        if m:
            value = m.group(1).strip(' ;:,.')
            # If a PDF layout joined a footnote sentence to the benchmark, trim common tails.
            value = re.split(r'\s+(?:There\s+is\s+an\s+allocation|The\s+benchmark\s+is|Disclaimer\s*:)', value, maxsplit=1, flags=re.I)[0].strip(' ;:,.')
            if value:
                return value
    # Fallback for layouts that split the label from the text or use lowercase.
    m = re.search(r'Current\s+benchmark\s*:\s*(.{1,300})', normalized, flags=re.I)
    if m:
        value = re.split(r'\s*\(\s*(?:w\.?\s*e\.?\s*f\.?|with\s+effect|effective|previous\s+benchmark)', m.group(1), maxsplit=1, flags=re.I)[0]
        return value.strip(' ;:,.')
    return 'Current benchmark not detected'


def extract_benchmark_components(benchmark):
    """Identify named benchmark index/rate components without inventing tickers."""
    if not benchmark or benchmark == 'Current benchmark not detected':
        return []
    # Capture weighted components such as '60% Index A and 40% Index B'.
    weighted = re.findall(r'(\d+(?:\.\d+)?\s*%\s*[^,;]+?)(?=\s+(?:and|\&)\s+\d+(?:\.\d+)?\s*%|$)', benchmark, flags=re.I)
    if weighted:
        components = []
        for item in weighted:
            item = item.strip(' .;,*')
            item = re.sub(r'^\s*(\d+(?:\.\d+)?)\s*%\s*', r'\1% ', item)
            components.append(item)
        # Ensure final weighted component is captured even where punctuation differs.
        if len(components) == 1 and re.search(r'\b\d+(?:\.\d+)?\s*%.*\b\d+(?:\.\d+)?\s*%', benchmark):
            parts = re.split(r'\s+(?:and|&)\s+', benchmark, flags=re.I)
            components = [x.strip(' .;,*') for x in parts if re.search(r'\d+(?:\.\d+)?\s*%', x)]
        return components
    return [benchmark.strip(' .;,*')]


def extract_info(text):
    normalized = clean_pdf_text(text)
    date_match = re.search(r'(?:As of|as at|As at|as of|Factsheet as at|as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', normalized, flags=re.I)
    benchmark = extract_current_benchmark(text)
    components = extract_benchmark_components(benchmark)
    return (date_match.group(1) if date_match else 'Not detected'), benchmark, components

@st.cache_data(ttl=900, show_spinner=False)
def latest_two_returns(ticker):
    data = yf.download(ticker, period='3mo', interval='1d', auto_adjust=False, progress=False, threads=False)
    if data is None or data.empty:
        raise ValueError('Yahoo Finance returned no daily data.')
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    # Index series usually has no dividend adjustment; use Adj Close when provided, otherwise Close.
    col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
    series = pd.to_numeric(data[col], errors='coerce').dropna()
    series = series[~series.index.duplicated(keep='last')].sort_index()
    returns = series.pct_change() * 100
    out = pd.DataFrame({'Date': series.index.strftime('%Y-%m-%d'), 'Index level': series.values, 'Daily return (%)': returns.values}).dropna()
    if len(out) < 2:
        raise ValueError('Fewer than two daily returns are available.')
    return out.tail(2).reset_index(drop=True)

st.title('📈 NAV price — Daily Benchmark Monitor')
st.caption('One-click test for five AIA funds: retrieve factsheets, identify benchmark wording, fetch available daily series, and consolidate results.')
st.info('Daily index data is fetched automatically. A successful ticker download does not prove that the ticker is the exact benchmark variant. Any proxy or unverified mapping is clearly labelled; missing values are not estimated.')

if st.button('Fetch all factsheets and daily returns', type='primary', use_container_width=True):
    rows, source_texts = [], {}
    progress = st.progress(0)
    for i, f in enumerate(FUNDS):
        row = {'Fund': f['fund'], 'Factsheet date': '—', 'Active benchmark (factsheet)': '—', 'Benchmark component(s) identified': '—', 'Benchmark data source': f['source'], 'Ticker': f['ticker'] or 'Not configured', 'T=0 date': '—', 'T=0 return': None, 'T−1 date': '—', 'T−1 return': None, 'Data status': '', 'Benchmark match / caveat': f['match']}
        try:
            text, size, pages = fetch_pdf(f['url'])
            asof, benchmark, components = extract_info(text)
            row['Factsheet date'] = asof
            row['Active benchmark (factsheet)'] = benchmark
            row['Benchmark component(s) identified'] = ' | '.join(components) if components else 'Not detected'
            source_texts[f['fund']] = {'text': text, 'url': f['url'], 'date': asof, 'benchmark': benchmark, 'components': components, 'size_kb': round(size/1024,1), 'pages': pages}
            if f['ticker']:
                try:
                    ret = latest_two_returns(f['ticker'])
                    prev, latest = ret.iloc[0], ret.iloc[1]
                    row['T=0 date'] = latest['Date']
                    row['T=0 return'] = round(float(latest['Daily return (%)']), 5)
                    row['T−1 date'] = prev['Date']
                    row['T−1 return'] = round(float(prev['Daily return (%)']), 5)
                    row['Data status'] = 'Daily series retrieved; benchmark mapping requires review'
                except Exception as e:
                    row['Data status'] = f'Factsheet OK; daily data failed: {str(e)[:180]}'
            else:
                row['Data status'] = 'Factsheet OK; no verified automatic daily series configured'
        except Exception as e:
            row['Data status'] = f'Factsheet download failed: {str(e)[:180]}'
        rows.append(row)
        progress.progress((i+1)/len(FUNDS))
    st.session_state['combined_rows'] = rows
    st.session_state['source_texts'] = source_texts

if 'combined_rows' in st.session_state:
    df = pd.DataFrame(st.session_state['combined_rows'])
    st.subheader('Consolidated benchmark and daily returns')
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        'T=0 return': st.column_config.NumberColumn(format='%.5f%%'),
        'T−1 return': st.column_config.NumberColumn(format='%.5f%%'),
        'Active benchmark (factsheet)': st.column_config.TextColumn(width='large'),
        'Benchmark component(s) identified': st.column_config.TextColumn(width='large'),
        'Benchmark match / caveat': st.column_config.TextColumn(width='large'),
        'Data status': st.column_config.TextColumn(width='large'),
    })
    st.download_button('Download consolidated results CSV', df.to_csv(index=False).encode('utf-8-sig'), 'nav_price_benchmark_returns.csv', 'text/csv')
    st.caption('T=0 is the latest available daily return in the source series; T−1 is the preceding available daily return. These are market-observation dates, not necessarily the current calendar date.')
    with st.expander('Inspect source factsheet text'):
        for fund, item in st.session_state.get('source_texts', {}).items():
            st.markdown(f"**{fund}** · factsheet date: {item['date']} · [Open PDF]({item['url']}) · {item['size_kb']} KB · {item['pages']} pages")
            st.write('Extracted current benchmark:', item['benchmark'])
            st.write('Benchmark component(s) identified:', item.get('components', []))
            st.text_area(f'Extracted PDF text — {fund}', item['text'][:12000], height=180, key='source_'+re.sub(r'\W+','_',fund))

st.divider()
st.markdown('**Coverage notes**')
st.markdown('''
- Benchmark parsing extracts the text following `Current benchmark:` and stops before effective-date/previous-benchmark metadata; weighted composite components are listed separately for review.
- **AIA US Equity Fund:** Yahoo Finance `^SP500TR` is labelled S&P 500 Total Return. The factsheet wording indicates a *Net Total Return* variant, so the downloaded series is shown only as an explicitly caveated approximation until an exact series is confirmed.
- **AIA Sustainable Multi-Thematic Fund:** Yahoo Finance `^990100-USD-STRD` is a candidate MSCI World series. Confirm the factsheet's currency and net/gross variant before relying on it as exact.
- **AIA Shariah Global Diversified Fund:** composite benchmark; the app does not calculate a weighted return until both components, weights and methodology are confirmed.
- **AIA S$ Money Market Fund:** deposit-rate benchmark; a daily percentage return may not be applicable.
- **AIA Regional Fixed Income Fund:** exact iBoxx SGD Overall total-return series is not yet configured.

The app now needs only one button click; it does not ask you to type tickers. Results with unverified benchmark mappings are labelled, not silently treated as exact.
''')
