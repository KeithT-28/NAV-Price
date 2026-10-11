import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="NAV price — Benchmark Chart", page_icon="📈", layout="wide")
st.title("Benchmark Chart")
st.caption("Separate chart page. The chart currently uses the S&P 500 price index as a clearly labelled proxy.")
try:
    r=requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",headers={"User-Agent":"Mozilla/5.0"},timeout=(5,12)); r.raise_for_status()
    df=pd.read_csv(StringIO(r.text)); date_col="observation_date" if "observation_date" in df.columns else "DATE"
    df[date_col]=pd.to_datetime(df[date_col],errors="coerce"); df["SP500"]=pd.to_numeric(df["SP500"],errors="coerce")
    df=df.dropna(subset=[date_col,"SP500"]).tail(250).set_index(date_col)
    st.line_chart(df["SP500"])
    st.caption("Source: FRED SP500, S&P 500 price index; not the net total return benchmark.")
except Exception as e:
    st.warning(f"Chart data unavailable: {type(e).__name__}: {str(e)[:160]}")
