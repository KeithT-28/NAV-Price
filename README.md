# NAV price — One-click Daily Benchmark Monitor

A Streamlit prototype for five AIA fund factsheets. It downloads the supplied Morningstar PDF links, extracts the factsheet date and candidate active benchmark wording, fetches daily historical data automatically for the two configured Yahoo Finance series, and combines everything into one table.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload `app.py`, `requirements.txt`, and this README.
3. Create a Streamlit app pointing to `app.py`.
4. Click **Fetch all factsheets and daily returns**.

## Important limitations

- Five Morningstar document URLs are currently configured in `app.py`.
- Yahoo Finance `^SP500TR` is a Total Return series and is not assumed to match the factsheet's S&P 500 Net Total Return variant exactly.
- Yahoo Finance `^990100-USD-STRD` is a candidate MSCI World series; currency and net/gross treatment must be verified against the latest factsheet.
- Composite Shariah, SGD 1-month deposit-rate, and iBoxx SGD Overall total-return benchmarks do not have verified automatic daily sources configured yet. They are shown as unavailable rather than guessed.
- `T=0` and `T−1` mean the two latest daily return observations returned by the source series, not today's and yesterday's calendar dates when markets are closed.
- Yahoo Finance availability and usage terms may change. This is a research/learning prototype, not investment advice.
