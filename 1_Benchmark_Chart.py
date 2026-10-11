import requests, pandas as pd, streamlit as st
from io import StringIO
st.set_page_config(page_title='NAV price — Benchmark chart',page_icon='📈',layout='wide')
st.title('📊 Benchmark chart')
st.caption('Chart is separate from the main consolidated returns table.')
HEADERS={'User-Agent':'Mozilla/5.0'}
SOURCES=[
 ('Yahoo Finance','https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1y&interval=1d&events=history','yahoo'),
 ('FRED','https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500','fred'),
 ('Stooq','https://stooq.com/q/d/l/?s=%5Espx&i=d','stooq')]
if st.button('Load benchmark chart',type='primary'):
    errors=[]; loaded=False
    for name,url,kind in SOURCES:
        try:
            r=requests.get(url,headers=HEADERS,timeout=(5,12)); r.raise_for_status()
            if kind=='yahoo':
                result=r.json()['chart']['result'][0]
                df=pd.DataFrame({'Date':pd.to_datetime(result['timestamp'],unit='s',utc=True).date,'Close':result['indicators']['quote'][0]['close']})
            elif kind=='fred':
                df=pd.read_csv(StringIO(r.text)); df=pd.DataFrame({'Date':pd.to_datetime(df['observation_date'],errors='coerce').dt.date,'Close':pd.to_numeric(df['SP500'],errors='coerce')})
            else:
                x=pd.read_csv(StringIO(r.text)); df=pd.DataFrame({'Date':pd.to_datetime(x['Date'],errors='coerce').dt.date,'Close':pd.to_numeric(x['Close'],errors='coerce')})
            df=df.dropna().sort_values('Date')
            if df.empty: raise ValueError('No observations returned')
            st.success(f'Loaded from {name}. This is the S&P 500 price index, not the factsheet’s net-total-return benchmark.')
            st.line_chart(df.set_index('Date')['Close'].tail(252))
            st.dataframe(df.tail(10),use_container_width=True,hide_index=True)
            st.markdown(f'[Open source data]({url})'); loaded=True; break
        except Exception as e: errors.append(f'{name}: {type(e).__name__}: {str(e)[:150]}')
    if not loaded:
        st.error('All configured data sources failed.'); st.write(errors)
else: st.write('Click to load approximately one year of daily closes. The page tries three sources in sequence.')
