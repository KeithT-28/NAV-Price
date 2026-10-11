import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
import streamlit as st
import fitz

st.set_page_config(page_title='NAV price', page_icon='📈', layout='wide')

FACTSHEETS = [
    {'fund':'AIA US Equity Fund','url':'https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Sustainable Multi-Thematic Fund','url':'https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Shariah Global Diversified Fund','url':'https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA S$ Money Market Fund','url':'https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
    {'fund':'AIA Regional Fixed Income Fund','url':'https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'},
]
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'}
# FRED's public CSV download endpoint does not require an API key. This series is the S&P 500 price index,
# NOT the S&P 500 Net Total Return benchmark in the AIA factsheet.
FRED_URL='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500'


def parse_benchmark(text):
    for m in re.finditer(r'current\s+benchmark\s*:\s*', text, re.I):
        tail=text[m.end():]
        cuts=[]
        for pat in [r'\s*\(\s*w\.e\.f\.?',r'\s*\(\s*with effect',r'\s*\(\s*effective',r'\s*\(\d+\)',r'\s+previous benchmark\s*:',r'\s+there is an allocation']:
            x=re.search(pat,tail,re.I)
            if x: cuts.append(x.start())
        end=min(cuts) if cuts else min(len(tail),240)
        val=re.sub(r'\s+',' ',tail[:end]).strip(' ;,:*')
        if val: return val
    return ''


def fetch_factsheet(item):
    try:
        r=requests.get(item['url'],headers=HEADERS,timeout=(8,25))
        r.raise_for_status()
        doc=fitz.open(stream=r.content,filetype='pdf')
        text='\n'.join(p.get_text('text') for p in doc)
        dm=re.search(r'(?:as at|as of|factsheet as at|data as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text,re.I)
        if not dm: dm=re.search(r'\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b',text)
        return {'Fund':item['fund'],'Factsheet date':dm.group(1) if dm else 'Date not detected','Active benchmark':parse_benchmark(text) or 'Current benchmark not detected','Factsheet status':'OK','Factsheet URL':item['url']},text
    except Exception as e:
        return {'Fund':item['fund'],'Factsheet date':'—','Active benchmark':'—','Factsheet status':f'Failed: {str(e)[:100]}','Factsheet URL':item['url']},''


def get_sp500_daily():
    r=requests.get(FRED_URL,headers=HEADERS,timeout=(8,25)); r.raise_for_status()
    df=pd.read_csv(StringIO(r.text))
    if not {'observation_date','SP500'}.issubset(df.columns):
        raise ValueError(f'Unexpected FRED CSV columns: {list(df.columns)}')
    df['observation_date']=pd.to_datetime(df['observation_date'],errors='coerce')
    df['SP500']=pd.to_numeric(df['SP500'],errors='coerce')
    df=df.dropna(subset=['observation_date','SP500']).sort_values('observation_date').reset_index(drop=True)
    df['Daily return (%)']=df['SP500'].pct_change()*100
    return df

st.title('📈 NAV price')
st.caption('AIA factsheet benchmark extraction and daily returns. Use the left navigation to open the separate chart page.')
st.info('Google Search is used to discover and cross-check sources; it is not a stable data API. This prototype retrieves daily S&P 500 price-index observations from FRED without an API key. That series is a proxy for checking the workflow and is NOT the exact S&P 500 Net Total Return benchmark.')

if st.button('Fetch factsheets and latest daily returns',type='primary'):
    facts=[]; texts={}
    bar=st.progress(0)
    for i,item in enumerate(FACTSHEETS):
        row,txt=fetch_factsheet(item); facts.append(row); texts[item['fund']]=txt
        bar.progress((i+1)/(len(FACTSHEETS)+1))
    try:
        daily=get_sp500_daily()
        if len(daily)<3: raise ValueError('Not enough daily observations returned.')
        latest=daily.iloc[-1]
        prev=daily.iloc[-2]
        prev2=daily.iloc[-3]
        # Latest return is close(T0)/close(T-1)-1; previous daily return is close(T-1)/close(T-2)-1.
        ret_t0=(latest['SP500']/prev['SP500']-1)*100
        ret_t1=(prev['SP500']/prev2['SP500']-1)*100
        benchmark_rows=[]
        for f in facts:
            exact=(f['Fund']=='AIA US Equity Fund')
            benchmark_rows.append({
                'Fund':f['Fund'],
                'Factsheet date':f['Factsheet date'],
                'Active benchmark (factsheet)':f['Active benchmark'],
                'Return data series':'S&P 500 price index (FRED SP500)' if exact else 'Not matched / not configured',
                'T=0 date':latest['observation_date'].date().isoformat() if exact else '—',
                'T=0 return':f"{ret_t0:+.4f}%" if exact else '—',
                'T−1 date':prev['observation_date'].date().isoformat() if exact else '—',
                'T−1 return':f"{ret_t1:+.4f}%" if exact else '—',
                'Data status':'Proxy only — price return, not net total return' if exact else 'Exact daily series not yet connected',
                'Factsheet URL':f['Factsheet URL']})
        st.session_state['facts']=facts
        st.session_state['texts']=texts
        st.session_state['results']=pd.DataFrame(benchmark_rows)
        st.session_state['daily']=daily
        bar.progress(1.0)
    except Exception as e:
        st.error(f'Could not retrieve daily S&P 500 data from FRED: {e}')

if 'results' in st.session_state:
    st.subheader('Consolidated daily benchmark returns')
    st.dataframe(st.session_state['results'].drop(columns=['Factsheet URL']),use_container_width=True,hide_index=True)
    st.download_button('Download consolidated results CSV',st.session_state['results'].to_csv(index=False).encode(),'nav_price_daily_returns.csv','text/csv')
    st.markdown(f'[Open FRED daily S&P 500 source]({FRED_URL}) · [Google Search: S&P 500 daily historical data](https://www.google.com/search?q=S%26P+500+daily+historical+data)')
    with st.expander('Inspect extracted factsheet text'):
        for fund,txt in st.session_state.get('texts',{}).items():
            st.markdown(f'**{fund}**')
            st.text_area(f'Source text — {fund}',txt[:10000] if txt else 'No text extracted.',height=140,key='text_'+fund)
else:
    st.write('Click the button to fetch the five factsheets and retrieve the latest available daily observations. The daily returns table uses the latest dates returned by the data source, not the current calendar date.')

st.caption('Data note: FRED SP500 is sourced from S&P Dow Jones Indices via FRED and represents the S&P 500 price index. It excludes dividend reinvestment, so it is not a substitute for the fund’s S&P 500 Net Total Return benchmark.')
