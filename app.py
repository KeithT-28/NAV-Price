import re, time
from io import StringIO
from datetime import datetime, timezone
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
YAHOO_URL='https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1mo&interval=1d&events=history'
FRED_URL='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500'
STOOQ_URL='https://stooq.com/q/d/l/?s=%5Espx&i=d'

def parse_benchmark(text):
    for m in re.finditer(r'current\s+benchmark\s*:\s*',text,re.I):
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
        r=requests.get(item['url'],headers=HEADERS,timeout=(8,20)); r.raise_for_status()
        if not r.content.startswith(b'%PDF'):
            raise ValueError('URL response was not a PDF')
        doc=fitz.open(stream=r.content,filetype='pdf')
        text='\n'.join(p.get_text('text') for p in doc)
        dm=re.search(r'(?:as at|as of|factsheet as at|data as at)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text,re.I)
        if not dm: dm=re.search(r'\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b',text)
        return {'Fund':item['fund'],'Factsheet date':dm.group(1) if dm else 'Date not detected','Active benchmark':parse_benchmark(text) or 'Current benchmark not detected','Factsheet status':'OK','Factsheet URL':item['url']},text
    except Exception as e:
        return {'Fund':item['fund'],'Factsheet date':'—','Active benchmark':'—','Factsheet status':f'Failed: {str(e)[:100]}','Factsheet URL':item['url']},''

def parse_yahoo():
    r=requests.get(YAHOO_URL,headers=HEADERS,timeout=(5,12)); r.raise_for_status()
    payload=r.json()['chart']
    if payload.get('error'): raise ValueError(str(payload['error']))
    result=payload['result'][0]
    closes=result['indicators']['quote'][0]['close']
    stamps=result['timestamp']
    df=pd.DataFrame({'Date':pd.to_datetime(stamps,unit='s',utc=True).date,'Close':closes})
    df['Close']=pd.to_numeric(df['Close'],errors='coerce')
    return df.dropna().sort_values('Date').reset_index(drop=True),'Yahoo Finance (^GSPC price index)',YAHOO_URL

def parse_fred():
    r=requests.get(FRED_URL,headers=HEADERS,timeout=(5,12)); r.raise_for_status()
    df=pd.read_csv(StringIO(r.text))
    date_col='observation_date' if 'observation_date' in df.columns else 'DATE'
    if date_col not in df.columns or 'SP500' not in df.columns: raise ValueError('Unexpected FRED CSV format')
    df['Date']=pd.to_datetime(df[date_col],errors='coerce').dt.date
    df['Close']=pd.to_numeric(df['SP500'],errors='coerce')
    return df[['Date','Close']].dropna().sort_values('Date').reset_index(drop=True),'FRED SP500 price index',FRED_URL

def parse_stooq():
    r=requests.get(STOOQ_URL,headers=HEADERS,timeout=(5,12)); r.raise_for_status()
    df=pd.read_csv(StringIO(r.text))
    if not {'Date','Close'}.issubset(df.columns): raise ValueError('Unexpected Stooq CSV format')
    df['Date']=pd.to_datetime(df['Date'],errors='coerce').dt.date
    df['Close']=pd.to_numeric(df['Close'],errors='coerce')
    return df[['Date','Close']].dropna().sort_values('Date').reset_index(drop=True),'Stooq ^SPX price-index series',STOOQ_URL

def fetch_daily_with_fallback():
    errors=[]
    for fn in (parse_yahoo,parse_fred,parse_stooq):
        try:
            df,source,url=fn()
            if len(df)<3: raise ValueError('Fewer than three valid daily observations')
            df['Daily return (%)']=df['Close'].pct_change()*100
            return df,source,url,errors
        except Exception as e:
            errors.append(f'{fn.__name__}: {type(e).__name__}: {str(e)[:160]}')
    raise RuntimeError('All daily sources failed. '+ ' | '.join(errors))

st.title('📈 NAV price')
st.caption('AIA factsheet benchmark extraction and daily returns. Use the left navigation for the separate chart page.')
st.info('This version tries Yahoo Finance first, then FRED, then Stooq. The configured S&P 500 series is a price-index proxy, not the exact S&P 500 Net Total Return benchmark in the AIA factsheet. The app keeps factsheet results even if daily data sources time out.')
if st.button('Fetch factsheets and latest daily returns',type='primary'):
    facts=[]; texts={}; bar=st.progress(0)
    for i,item in enumerate(FACTSHEETS):
        row,txt=fetch_factsheet(item); facts.append(row); texts[item['fund']]=txt
        bar.progress((i+1)/(len(FACTSHEETS)+1))
    st.session_state['facts']=facts; st.session_state['texts']=texts
    try:
        daily,source,source_url,errors=fetch_daily_with_fallback()
        latest=daily.iloc[-1]; prev=daily.iloc[-2]; prev2=daily.iloc[-3]
        t0=(latest['Close']/prev['Close']-1)*100
        t1=(prev['Close']/prev2['Close']-1)*100
        rows=[]
        for f in facts:
            is_us=f['Fund']=='AIA US Equity Fund'
            rows.append({'Fund':f['Fund'],'Factsheet date':f['Factsheet date'],'Active benchmark (factsheet)':f['Active benchmark'],
              'Daily series':source if is_us else 'Not matched to exact benchmark','T=0 date':str(latest['Date']) if is_us else '—',
              'T=0 return':f'{t0:+.4f}%' if is_us else '—','T−1 date':str(prev['Date']) if is_us else '—',
              'T−1 return':f'{t1:+.4f}%' if is_us else '—',
              'Data status':'Proxy only — price return, not net total return' if is_us else 'Exact daily series not yet connected',
              'Source URL':source_url if is_us else '', 'Factsheet URL':f['Factsheet URL']})
        st.session_state['daily']=daily; st.session_state['daily_source']=source; st.session_state['daily_url']=source_url
        st.session_state['results']=pd.DataFrame(rows); st.session_state['source_errors']=errors
    except Exception as e:
        st.session_state.pop('results',None)
        st.session_state['daily_error']=str(e)
    bar.progress(1.0)

if 'facts' in st.session_state:
    st.subheader('Factsheet benchmark extraction')
    st.dataframe(pd.DataFrame(st.session_state['facts']).drop(columns=['Factsheet URL']),use_container_width=True,hide_index=True)
if 'results' in st.session_state:
    st.subheader('Consolidated daily benchmark returns')
    st.dataframe(st.session_state['results'].drop(columns=['Source URL','Factsheet URL']),use_container_width=True,hide_index=True)
    st.download_button('Download consolidated results CSV',st.session_state['results'].to_csv(index=False).encode(),'nav_price_daily_returns.csv','text/csv')
    st.markdown(f"[Open daily source]({st.session_state['daily_url']})")
    if st.session_state.get('source_errors'):
        with st.expander('Fallback source diagnostics'):
            st.write('A previous source failed; a later source succeeded.')
            for err in st.session_state['source_errors']: st.write('• '+err)
if st.session_state.get('daily_error'):
    st.warning('Factsheets were still processed, but no daily source responded successfully.')
    st.code(st.session_state['daily_error'])
if 'texts' in st.session_state:
    with st.expander('Inspect extracted factsheet text'):
        for fund,txt in st.session_state['texts'].items():
            st.markdown(f'**{fund}**'); st.text_area(f'Source text — {fund}',txt[:10000] if txt else 'No text extracted.',height=140,key='text_'+re.sub(r'\W+','_',fund))
st.caption('Returns are calculated from consecutive valid daily closes. The latest available trading date is used, not the current calendar date. Proxy returns must not be confused with exact benchmark returns.')
