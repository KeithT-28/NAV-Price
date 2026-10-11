import re, time
from io import StringIO
import pandas as pd
import requests
import streamlit as st
import fitz

st.set_page_config(page_title="NAV price", page_icon="📈", layout="wide")
FACTSHEETS = [
 {"fund":"AIA US Equity Fund","url":"https://doc.morningstar.com/Document/56e50cc5aa606c0161d09d15cc7de5ad.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"},
 {"fund":"AIA Sustainable Multi-Thematic Fund","url":"https://doc.morningstar.com/Document/14881aad057e7317a556204fc79e64a7.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"},
 {"fund":"AIA Shariah Global Diversified Fund","url":"https://doc.morningstar.com/Document/88e47b70c3bb196bc7d20acc4dab51cc.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"},
 {"fund":"AIA S$ Money Market Fund","url":"https://doc.morningstar.com/Document/276e48d297edd7cc1111ea906b64a100.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"},
 {"fund":"AIA Regional Fixed Income Fund","url":"https://doc.morningstar.com/Document/6cf9c99b91ed64fc3af226442a4ee366.msdoc/?key=fe676c95ebbe14133d9103ba59358bd91d52b060dfdbd81e81f60e7e14394d07"},
]
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
TIMEOUT=(5,12)

def clean_benchmark_text(text):
    text=re.sub(r'\s+',' ',text).strip()
    # Remove footnote/disclaimer prose which sometimes follows benchmark name.
    for pat in [r'\.\s*\*?there is an allocation\b', r'\s+\*\s*there is an allocation\b',
                r'\s+management\s+(?:private\s+)?(?:limited|pte ltd)\b']:
        m=re.search(pat,text,re.I)
        if m: text=text[:m.start()].strip()
    return text.strip(' ;,:*')

def parse_benchmark(text):
    # Find the most recent/current benchmark wording in PDF text.
    matches=list(re.finditer(r'current\s+benchmark\s*:\s*',text,re.I))
    for m in matches:
        tail=text[m.end():]
        cuts=[]
        for pat in [r'\s*\(\s*w\.e\.f\.?',r'\s*\(\s*with effect',r'\s*\(\s*effective',
                    r'\s*\(\s*\d+\s*\)',r'\s+previous benchmark\s*:',r'\s+\*\s*there is an allocation']:
            x=re.search(pat,tail,re.I)
            if x: cuts.append(x.start())
        end=min(cuts) if cuts else min(len(tail),300)
        val=clean_benchmark_text(tail[:end])
        if val: return val
    # Some factsheets use different punctuation/capitalisation or text ordering.
    return ''

def split_components(benchmark):
    """Return weighted components when explicit percentages exist; otherwise one component."""
    b=clean_benchmark_text(benchmark)
    if not b or b.lower() in ('current benchmark not detected','—','-'):
        return []
    # Capture forms such as '60% MSCI ... and 40% Dow Jones ...'.
    matches=list(re.finditer(r'(\d+(?:\.\d+)?)\s*%\s*',b))
    if len(matches)>=2:
        out=[]
        for i,m in enumerate(matches):
            start=m.end()
            end=matches[i+1].start() if i+1<len(matches) else len(b)
            name=b[start:end].strip(' ,;:*')
            name=re.sub(r'\s+\band\b\s*$','',name,flags=re.I).strip()
            name=clean_benchmark_text(name)
            if name:
                out.append({'Weight (%)':float(m.group(1)),'Benchmark component':name})
        if out and abs(sum(x['Weight (%)'] for x in out)-100)>0.1:
            # Keep detected weights visible; do not silently normalise them.
            pass
        return out
    return [{'Weight (%)':100.0,'Benchmark component':b}]

def fetch_factsheet(item):
    try:
        r=requests.get(item['url'],headers=HEADERS,timeout=TIMEOUT); r.raise_for_status()
        if not r.content.startswith(b'%PDF'): raise ValueError('Response was not a PDF')
        doc=fitz.open(stream=r.content,filetype='pdf')
        text='\n'.join(p.get_text('text') for p in doc)
        dm=re.search(r'(?:as at|as of|factsheet as at|data as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text,re.I)
        if not dm: dm=re.search(r'\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b',text)
        bench=parse_benchmark(text)
        return {'Fund':item['fund'],'Factsheet date':dm.group(1) if dm else 'Date not detected','Active benchmark':bench or 'Current benchmark not detected','Factsheet status':'OK','Factsheet URL':item['url']},text
    except Exception as e:
        return {'Fund':item['fund'],'Factsheet date':'—','Active benchmark':'Current benchmark not detected','Factsheet status':f'Failed: {type(e).__name__}: {str(e)[:90]}','Factsheet URL':item['url']},''

def fetch_sp500_proxy():
    # Public FRED CSV: S&P 500 price index only, not net total return.
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500'
    r=requests.get(url,headers=HEADERS,timeout=TIMEOUT); r.raise_for_status()
    df=pd.read_csv(StringIO(r.text))
    date_col='observation_date' if 'observation_date' in df.columns else 'DATE'
    if date_col not in df.columns or 'SP500' not in df.columns: raise ValueError('Unexpected FRED CSV schema')
    df['Date']=pd.to_datetime(df[date_col],errors='coerce').dt.date
    df['Close']=pd.to_numeric(df['SP500'],errors='coerce')
    df=df[['Date','Close']].dropna().sort_values('Date').reset_index(drop=True)
    if len(df)<3: raise ValueError('Not enough daily observations')
    df['Return (%)']=df['Close'].pct_change()*100
    return df,'FRED — S&P 500 price index','https://fred.stlouisfed.org/series/SP500'

def component_data(component):
    """Only return series with a deliberate, disclosed mapping. Never guess a ticker."""
    name=component.lower()
    if 'standard poor' in name or 's&p 500' in name:
        try:
            df,source,url=fetch_sp500_proxy()
            latest,prev,prevprev=df.iloc[-1],df.iloc[-2],df.iloc[-3]
            return {'Source':source,'Ticker / series':'FRED: SP500','T=0 date':str(latest['Date']),
                    'T=0 return (%)':round(float(latest['Return (%)']),6),'T−1 date':str(prev['Date']),
                    'T−1 return (%)':round(float(prev['Return (%)']),6),
                    'Status':'PROXY ONLY — price return, not net total return','Source URL':url}
        except Exception as e:
            return {'Source':'FRED','Ticker / series':'SP500','T=0 date':'—','T=0 return (%)':None,'T−1 date':'—','T−1 return (%)':None,'Status':f'Fetch failed: {type(e).__name__}','Source URL':'https://fred.stlouisfed.org/series/SP500'}
    return {'Source':'Not connected','Ticker / series':'—','T=0 date':'—','T=0 return (%)':None,'T−1 date':'—','T−1 return (%)':None,
            'Status':'Exact component series not yet verified','Source URL':''}

st.title('📈 NAV price')
st.caption('Benchmark components and daily returns. Composite benchmarks are split into separate component rows.')
st.info('This version extracts explicit benchmark weights and lists every component separately. It only fills returns where a data series is deliberately mapped; unknown components remain blank rather than being assigned a guessed ticker.')
if st.button('Fetch factsheets and component returns',type='primary'):
    facts=[]; texts={}; components=[]; bar=st.progress(0)
    for i,item in enumerate(FACTSHEETS):
        row,txt=fetch_factsheet(item); facts.append(row); texts[item['fund']]=txt
        comps=split_components(row['Active benchmark'])
        if not comps:
            components.append({'Fund':item['fund'],'Factsheet date':row['Factsheet date'],'Active benchmark':row['Active benchmark'],
                               'Weight (%)':None,'Benchmark component':'—','Source':'—','Ticker / series':'—','T=0 date':'—',
                               'T=0 return (%)':None,'T−1 date':'—','T−1 return (%)':None,'Status':'Benchmark not extracted','Source URL':''})
        else:
            for comp in comps:
                data=component_data(comp['Benchmark component'])
                components.append({'Fund':item['fund'],'Factsheet date':row['Factsheet date'],'Active benchmark':row['Active benchmark'],
                                   'Weight (%)':comp['Weight (%)'],'Benchmark component':comp['Benchmark component'],**data})
        bar.progress((i+1)/len(FACTSHEETS))
    st.session_state['facts']=facts
    st.session_state['components']=pd.DataFrame(components)
    st.session_state['texts']=texts

if 'facts' in st.session_state:
    st.subheader('Active benchmarks extracted from factsheets')
    st.dataframe(pd.DataFrame(st.session_state['facts']).drop(columns=['Factsheet URL']),use_container_width=True,hide_index=True)
if 'components' in st.session_state:
    st.subheader('Daily returns by benchmark component')
    st.caption('For a weighted benchmark, each component gets its own row and return columns. T=0/T−1 are the two latest available observations for that component, not necessarily the same dates across providers.')
    df=st.session_state['components']
    st.dataframe(df.drop(columns=['Source URL']),use_container_width=True,hide_index=True)
    st.download_button('Download component-level returns CSV',df.to_csv(index=False).encode(),'nav_price_component_returns.csv','text/csv')
    with st.expander('How composite benchmarks are handled'):
        st.write('The app extracts explicit percentage weights (for example, 60% and 40%) and creates a separate row for each named component. It does not calculate a blended benchmark return unless the exact component series, dates, currency, return type and weighting methodology have been verified.')
if 'texts' in st.session_state:
    with st.expander('Inspect source PDF text'):
        for fund,txt in st.session_state['texts'].items():
            st.markdown(f'**{fund}**')
            st.text_area(f'Source text — {fund}',txt[:10000] if txt else 'No text extracted.',height=140,key='text_'+re.sub(r'\W+','_',fund))
st.caption('Daily returns are calculated from consecutive valid daily index observations. Source variants matter: price return, gross total return and net total return are not interchangeable.')
