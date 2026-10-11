import io, re, time
from datetime import date
import pandas as pd
import requests
import streamlit as st
import fitz

st.set_page_config(page_title='NAV price | Daily Benchmark Monitor', page_icon='📈', layout='wide')

KEY='fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07'
FUNDS = [
    {'fund':'AIA US Equity Fund','url':f'https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key={KEY}'},
    {'fund':'AIA Sustainable Multi-Thematic Fund','url':f'https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key={KEY}'},
    {'fund':'AIA Shariah Global Diversified Fund','url':f'https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key={KEY}'},
    {'fund':'AIA S$ Money Market Fund','url':f'https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key={KEY}'},
    {'fund':'AIA Regional Fixed Income Fund','url':f'https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key={KEY}'},
]
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; NAVPriceResearch/1.0)'}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pdf(url):
    r=requests.get(url, headers=HEADERS, timeout=(8,25))
    r.raise_for_status()
    if not (r.content[:4] == b'%PDF' or 'pdf' in r.headers.get('Content-Type','').lower()):
        raise ValueError(f"Response does not look like a PDF (Content-Type: {r.headers.get('Content-Type','unknown')})")
    doc=fitz.open(stream=r.content, filetype='pdf')
    text='\n'.join(p.get_text('text') for p in doc)
    return text, len(r.content), len(doc)

def extract_info(text):
    lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if x.strip()]
    date_match=re.search(r'(?:As of|as at|As at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', text)
    # Capture benchmark-related notes and wording conservatively; never invent a benchmark.
    candidates=[]
    for i,line in enumerate(lines):
        low=line.lower()
        if 'benchmark' in low or 'index' in low and ('return' in low or '%' in low):
            candidates.append(' '.join(lines[max(0,i-1):min(len(lines),i+3)]))
    # De-duplicate, preserve document order.
    seen=set(); candidates=[x for x in candidates if not (x in seen or seen.add(x))]
    # Try to identify current benchmark note explicitly.
    current=[]
    for line in lines:
        if re.search(r'current benchmark|benchmark\s*:', line, re.I): current.append(line)
    benchmark=' '.join(current) if current else (' '.join(candidates[:4]) if candidates else 'No benchmark wording confidently detected')
    return date_match.group(1) if date_match else 'Not detected', benchmark, candidates

def calculate_returns(df):
    cols={c.lower().strip():c for c in df.columns}
    date_col=next((cols[k] for k in cols if k in ('date','datetime','observation date','index date')),None)
    val_col=next((cols[k] for k in cols if k in ('level','index level','close','value','index value','price')),None)
    if not date_col or not val_col:
        raise ValueError('CSV needs columns named Date and Level (or Close/Value).')
    d=df[[date_col,val_col]].copy(); d.columns=['Date','Level']
    d['Date']=pd.to_datetime(d['Date'], errors='coerce'); d['Level']=pd.to_numeric(d['Level'].astype(str).str.replace(',',''), errors='coerce')
    d=d.dropna().sort_values('Date').drop_duplicates('Date',keep='last')
    if len(d)<2: raise ValueError('Need at least two valid daily index levels.')
    d['Daily return (%)']=d['Level'].pct_change()*100
    latest=d.iloc[-1]; prev=d.iloc[-2]
    return {'T0 date':latest['Date'].date().isoformat(),'T0 level':float(latest['Level']),'T0 return (%)':float(latest['Daily return (%)']) if pd.notna(latest['Daily return (%)']) else None,
            'T-1 date':prev['Date'].date().isoformat(),'T-1 level':float(prev['Level']),'T-1 return (%)':float(d.iloc[-2]['Daily return (%)']) if len(d)>2 and pd.notna(d.iloc[-2]['Daily return (%)']) else None}

st.title('📈 NAV price — Daily Benchmark Monitor')
st.caption('Five-fund prototype · factsheet benchmark identification + daily benchmark return comparison')
st.info('This version reads the benchmark from each official factsheet PDF. Daily returns require exact benchmark-level data. It does not silently substitute a similar index or estimate missing values.')

with st.expander('Five factsheet URLs', expanded=False):
    for i,f in enumerate(FUNDS,1): st.markdown(f"{i}. [{f['fund']}]({f['url']})")

if st.button('Fetch latest factsheets and identify benchmark notes', type='primary'):
    rows=[]; details={}
    progress=st.progress(0)
    for i,f in enumerate(FUNDS):
        start=time.time()
        try:
            text,size,pages=fetch_pdf(f['url'])
            asof,bm,candidates=extract_info(text)
            rows.append({'Fund':f['fund'],'PDF status':'OK','Factsheet date':asof,'Benchmark candidate':bm,'Size (KB)':round(size/1024,1),'Pages':pages,'Seconds':round(time.time()-start,2)})
            details[f['fund']]={'text':text,'benchmark':bm,'candidates':candidates,'date':asof,'url':f['url']}
        except Exception as e:
            rows.append({'Fund':f['fund'],'PDF status':f'FAILED: {str(e)[:120]}','Factsheet date':'—','Benchmark candidate':'—','Size (KB)':None,'Pages':None,'Seconds':round(time.time()-start,2)})
        progress.progress((i+1)/len(FUNDS))
    st.session_state['factsheet_rows']=rows; st.session_state['factsheet_details']=details

if 'factsheet_rows' in st.session_state:
    st.subheader('Factsheet scan results')
    st.dataframe(pd.DataFrame(st.session_state['factsheet_rows']),use_container_width=True,hide_index=True)
    details=st.session_state['factsheet_details']
    if details:
        fund=st.selectbox('Inspect benchmark wording',list(details.keys()))
        info=details[fund]
        st.markdown(f"**Factsheet date:** {info['date']}  \n**PDF:** [Open source factsheet]({info['url']})")
        st.markdown('**Benchmark wording detected**')
        st.write(info['benchmark'])
        with st.expander('Candidate benchmark/index lines'):
            for c in info['candidates']: st.write('• '+c)
        with st.expander('Extracted source text (for verification)'):
            st.text(info['text'][:20000])

st.divider()
st.header('Daily returns: T=0 vs T−1')
st.write('Upload daily index-level CSVs from a credible provider for the exact benchmark variant named in the factsheet. For each fund, use a CSV with at least three dates and columns `Date` and `Level` (or `Close`/`Value`). The app computes returns from consecutive available index levels.')
st.warning('Important: a benchmark name alone is not enough to select an equivalent free ticker. Examples such as S&P 500 price return are not the same as S&P 500 Net Total Return. Official daily index levels may require provider registration or a licence. Confirm exact variant, currency and total-return treatment before using the figures.')

fund=st.selectbox('Fund to attach daily benchmark data to', [f['fund'] for f in FUNDS], key='daily_fund')
source=st.text_input('Data source / index provider URL (for audit trail)', placeholder='e.g. official index provider page or licensed data export')
upload=st.file_uploader('Upload benchmark daily index levels (CSV)', type=['csv'], key='daily_csv')
if upload is not None:
    try:
        data=pd.read_csv(upload)
        result=calculate_returns(data)
        st.success('Daily returns calculated from the uploaded index levels.')
        st.caption(f"Fund: {fund} · Source recorded: {source or 'Not supplied'}")
        out=pd.DataFrame([{'Fund':fund,'Benchmark/source':source or 'User-uploaded CSV','T=0 date':result['T0 date'],'T=0 daily return (%)':result['T0 return (%)'],'T−1 date':result['T-1 date'],'T−1 daily return (%)':result['T-1 return (%)']}])
        st.dataframe(out,use_container_width=True,hide_index=True)
        st.download_button('Download daily return row (CSV)',out.to_csv(index=False).encode(),file_name='nav_price_daily_benchmark_return.csv',mime='text/csv')
        with st.expander('Index levels used'):
            st.dataframe(data.tail(10),use_container_width=True,hide_index=True)
    except Exception as e: st.error(str(e))
else:
    st.caption('No daily return is shown until index-level data is supplied; this avoids inventing or mislabelling returns.')

st.divider()
st.subheader('Next step for automatic daily data')
st.markdown('For the next iteration, connect a provider only after confirming it exposes the exact benchmark variant and permits automated retrieval. Potential official providers include [MSCI](https://www.msci.com/indexes), [S&P Dow Jones Indices](https://www.spglobal.com/spdji/en/), and [S&P Global iBoxx](https://www.spglobal.com/marketintelligence/en/solutions/indices). The SGD money-market benchmark may be a deposit rate rather than a traded index, so it may need a separate source and return convention.')
