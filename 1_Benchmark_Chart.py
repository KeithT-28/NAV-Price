from io import StringIO
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='NAV price — Benchmark chart', page_icon='📈', layout='wide')
st.title('📊 Benchmark chart')
st.caption('The chart is kept on this separate page so the main NAV price page can focus on the consolidated daily returns table.')
st.info('This chart currently uses the S&P 500 price index from FRED as a visual reference. It is not the exact S&P 500 Net Total Return benchmark stated in the AIA US Equity Fund factsheet.')
url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500'
if st.button('Load S&P 500 chart',type='primary'):
    try:
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=(8,25)); r.raise_for_status()
        df=pd.read_csv(StringIO(r.text))
        df['observation_date']=pd.to_datetime(df['observation_date'],errors='coerce')
        df['SP500']=pd.to_numeric(df['SP500'],errors='coerce')
        df=df.dropna(subset=['observation_date','SP500']).sort_values('observation_date')
        st.line_chart(df.set_index('observation_date')['SP500'].tail(252))
        st.dataframe(df.tail(10).rename(columns={'observation_date':'Date','SP500':'S&P 500 close'}),use_container_width=True,hide_index=True)
        st.markdown(f'[Open source data]({url})')
    except Exception as e:
        st.error(f'Could not load chart data: {e}')
else:
    st.write('Click the button to load approximately one year of daily closes.')
