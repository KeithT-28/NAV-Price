# NAV price — Google-discovered sources prototype

## Pages
- Main page: fetches five Morningstar factsheets, extracts current benchmark wording, and shows a consolidated T=0 / T-1 daily-return table.
- Benchmark Chart page: separate chart page, as requested.

## Data source note
The prototype retrieves FRED's public CSV for `SP500` without an API key. FRED attributes the series to S&P Dow Jones Indices. It is the S&P 500 price index, not the exact `S&P 500 Net Total Return` benchmark in the AIA US Equity Fund factsheet. The app labels it as a proxy and does not fill returns for the other four funds until exact matching series are found.

Google Search is used to discover and cross-check public sources, but scraping search-result pages is not a reliable data interface. The app links to Google Search and the underlying FRED source rather than treating snippets as data.

## Deploy
Upload `app.py`, `requirements.txt`, the `pages/` folder and this README to a GitHub repository. Deploy `app.py` on Streamlit Community Cloud.
