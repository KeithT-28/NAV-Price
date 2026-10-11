import re, time
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
import fitz
import yfinance as yf

st.set_page_config(page_title='NAV price | Automated Benchmark Returns', page_icon='📈', layout='wide')
KEY='fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'
FUNDS=[
 {'fund':'AIA US Equity Fund','url':f'https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key={KEY}','default_ticker':'','note':'Ticker will only be suggested after confirming the benchmark wording in the PDF.'},
 {'fund':'AIA Sustainable Multi-Thematic Fund','url':f'https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key={KEY}','default_ticker':'^990100-USD-STRD','note':'Yahoo Finance lists this ticker as MSCI World Index in USD. Verify the factsheet uses the same currency and return variant.'},
 {'fund':'AIA Shariah Global Diversified Fund','url':f'https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key={KEY}','default_ticker':'','note':'Composite benchmark: do not substitute one component for the full blended benchmark.'},
 {'fund':'AIA S$ Money Market Fund','url':f'https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key={KEY}','default_ticker':'','note':'A deposit-rate benchmark may not have a meaningful daily index-level series.'},
 {'fund':'AIA Regional Fixed Income Fund','url':f'https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key={KEY}','default_ticker':'','note':'Exact iBoxx total-return benchmark availability must be verified; do not substitute a bond ETF.'},
]
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; NAVPriceResearch/1.0)'}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pdf(url):
    r=requests.get(url,headers=HEADERS,timeout=(8,25)); r.raise_for_status()
    if r.content[:4] != b'%PDF' and 'pdf' not in r.headers.get('Content-Type','').lower():
        raise ValueError(f"Response is not a PDF (Content-Type: {r.headers.get('Content-Type','unknown')})")
    doc=fitz.open(stream=r.content,filetype='pdf')
    return '\n'.join(p.get_text('text') for p in doc),len(r.content),len(doc)

def extract_info(text):
    lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if x.strip()]
    date_match=re.search(r'(?:As of|as at|As at|as of)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text)
    snippets=[]
    for i,line in enumerate(lines):
        if 'benchmark' in line.lower(): snippets.append(' '.join(lines[max(0,i-1):min(len(lines),i+4)]))
    unique=[]
    for x in snippets:
        if x not in unique: unique.append(x)
    explicit=[x for x in lines if re.search(r'current benchmark|benchmark\s*:',x,re.I)]
    benchmark=' '.join(explicit) if explicit else (' | '.join(unique[:5]) if unique else 'No benchmark wording confidently detected')
    return date_match.group(1) if date_match else 'Not detected',benchmark,unique

@st.cache_data(ttl=900,show_spinner=False)
def yahoo_history(ticker,period='1mo'):
    data=yf.download(ticker,period=period,interval='1d',auto_adjust=False,progress=False,threads=False)
    if data is None or data.empty: raise ValueError('Yahoo Finance returned no daily history for this ticker.')
    if isinstance(data.columns,pd.MultiIndex): data.columns=data.columns.get_level_values(0)
    col='Adj Close' if 'Adj Close' in data.columns else 'Close'
    series=pd.to_numeric(data[col],errors='coerce').dropna()
    series=series[~series.index.duplicated(keep='last')].sort_index()
    if len(series)<3: raise ValueError('Fewer than three daily observations; need three closes to calculate T=0 and T-1 returns.')
    ret=series.pct_change()*100
    # Most recent available observation and the prior observation; each return is measured versus its own prior close.
    return pd.DataFrame({'Date':series.index.date.astype(str),'Index level':series.values,'Daily return (%)':ret.values}).dropna().tail(2).reset_index(drop=True)

st.title('📈 NAV price — Automated Daily Benchmark Returns')
st.caption('Five-fund prototype · factsheet benchmark extraction + automated Yahoo Finance history where an exact ticker is available')
st.info('No CSV upload is required. The app fetches factsheets and daily series automatically. It will not silently substitute a proxy index for an exact benchmark. Yahoo Finance data is for informational use; check provider terms before redistributing it.')

st.subheader('1. Identify the benchmark from each latest factsheet')
if st.button('Fetch factsheets and extract benchmark wording',type='primary'):
    rows=[]; details={}; bar=st.progress(0)
    for i,f in enumerate(FUNDS):
        try:
            text,size,pages=fetch_pdf(f['url']); asof,bm,cands=extract_info(text)
            rows.append({'Fund':f['fund'],'PDF':'OK','Factsheet date':asof,'Benchmark wording':bm,'KB':round(size/1024,1),'Pages':pages})
            details[f['fund']]={'text':text,'date':asof,'benchmark':bm,'candidates':cands,'url':f['url']}
        except Exception as e:
            rows.append({'Fund':f['fund'],'PDF':'FAILED','Factsheet date':'—','Benchmark wording':str(e),'KB':None,'Pages':None})
        bar.progress((i+1)/len(FUNDS))
    st.session_state['factsheet_rows']=rows; st.session_state['factsheet_details']=details
if 'factsheet_rows' in st.session_state:
    st.dataframe(pd.DataFrame(st.session_state['factsheet_rows']),use_container_width=True,hide_index=True)
    with st.expander('Inspect source PDF text for each fund'):
        for fund,d in st.session_state['factsheet_details'].items():
            st.markdown(f"**{fund}** · factsheet date: {d['date']} · [Open PDF]({d['url']})")
            st.text_area(f'Extracted text — {fund}',d['text'][:12000],height=180,key='txt_'+re.sub(r'\W+','_',fund))

st.divider(); st.subheader('2. Fetch daily benchmark returns automatically')
st.write('Enter a Yahoo Finance ticker only when it represents the exact benchmark variant shown in the factsheet. For composite benchmarks, use a source and calculation method that matches the official methodology.')
results=[]
for f in FUNDS:
    with st.container(border=True):
        st.markdown(f"**{f['fund']}**")
        st.caption(f['note'])
        default=f['default_ticker']
        ticker=st.text_input('Yahoo Finance ticker',value=default,key='ticker_'+re.sub(r'\W+','_',f['fund']),placeholder='e.g. ^990100-USD-STRD')
        if ticker:
            st.markdown(f'[Open ticker history on Yahoo Finance](https://finance.yahoo.com/quote/{ticker.replace("^","%5E")}/history/)')
        if st.button('Fetch daily returns',key='fetch_'+re.sub(r'\W+','_',f['fund'])):
            if not ticker.strip(): st.warning('No ticker configured. We will not guess a ticker for this benchmark.')
            else:
                with st.spinner(f'Fetching {ticker} history…'):
                    try:
                        d=yahoo_history(ticker.strip())
                        d.insert(0,'Fund',f['fund']); d.insert(1,'Ticker',ticker.strip())
                        st.dataframe(d,use_container_width=True,hide_index=True)
                        if len(d)>=2:
                            latest=d.iloc[-1]; previous=d.iloc[-2]
                            st.success(f"Latest available daily return (T=0): {latest['Daily return (%)']:.4f}% on {latest['Date']} · Previous daily return (T−1): {previous['Daily return (%)']:.4f}% on {previous['Date']}.")
                        st.caption('Source: Yahoo Finance historical data. Returns are calculated from consecutive daily adjusted closes when available; dates follow the ticker’s market calendar.')
                    except Exception as e: st.error(f'Could not retrieve data: {e}')

st.divider()
st.subheader('Data coverage notes')
st.markdown('''
- **MSCI World:** Yahoo Finance lists `^990100-USD-STRD` as MSCI World in USD. This is only appropriate if it matches the factsheet's exact currency and return variant.
- **Composite benchmark:** AIA Shariah Global Diversified Fund requires both components and the official weights/methodology. One component alone is not the benchmark.
- **Money-market benchmark:** a quoted deposit rate may be a rate observation rather than a daily index level, so daily index returns may not be available or meaningful.
- **iBoxx fixed-income benchmark:** if the exact total-return series is not available free on Yahoo Finance, the app should report that and we should investigate the index provider. Do not substitute a bond ETF without explicitly labelling it a proxy.
- Yahoo Finance states its data is provided as-is and should not be redistributed. Review applicable terms before publishing or redistributing outputs.
''')
