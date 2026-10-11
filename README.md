# NAV price — Benchmark component returns

## What this version does
- Downloads the five supplied Morningstar factsheet PDFs.
- Extracts the current benchmark wording.
- Splits explicit weighted benchmarks (e.g. `60% Index A and 40% Index B`) into separate component rows with their weights.
- Attempts daily return retrieval only for a deliberately configured series: the S&P 500 price index from FRED, clearly labelled as a proxy rather than the S&P 500 Net Total Return benchmark.
- Leaves other component returns blank until an exact source/variant is verified.
- Exports a component-level CSV.

## Deploy
Upload `app.py`, `requirements.txt`, and this README to Streamlit Community Cloud. Set the main file to `app.py`.

## Important
This is not yet a complete data feed. It does not guess tickers for MSCI AC World Islamic, Dow Jones Sukuk, the SGD deposit rate, or Markit iBoxx SGD Overall TR. Exact series and licensing/access must be verified before connecting returns. Composite benchmark returns are not calculated merely by averaging component daily returns.
