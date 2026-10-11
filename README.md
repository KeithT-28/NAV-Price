# NAV price — resilient daily data test

This version fixes the previous failure mode: a FRED timeout no longer prevents the factsheet table from appearing. It attempts daily S&P 500 price-index data from Yahoo Finance, then FRED, then Stooq, with short per-request timeouts. Factsheet extraction and daily-data retrieval are handled independently.

## Deploy
Upload `app.py`, `requirements.txt`, `README.md`, and `pages/1_Benchmark_Chart.py` to the repository and redeploy Streamlit Community Cloud.

## Important data limitation
The S&P 500 series used here is a **price index proxy**, not the exact S&P 500 Net Total Return benchmark stated in the AIA US Equity Fund factsheet. It is only used to test retrieval and table flow. Other fund rows remain blank until an exact series and source are verified. Public endpoints can fail or change; the app reports failure rather than inventing data.

## Sources attempted
- Yahoo Finance chart endpoint for `^GSPC`
- FRED public CSV for `SP500`
- Stooq daily CSV for `^SPX`

The app keeps factsheet results visible even if all daily sources time out. The chart is on a separate Streamlit page.
