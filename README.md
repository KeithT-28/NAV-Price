# NAV price — Investing.com source test

This Streamlit prototype tests retrieval of five user-provided Morningstar PDF factsheets and daily historical data from Investing.com without a paid API or manual CSV upload.

## Deploy
1. Create a new GitHub repository.
2. Upload `app.py`, `requirements.txt`, and `README.md`.
3. Deploy `app.py` on Streamlit Community Cloud.
4. Click **Fetch factsheets and test Investing.com**.

## Important limitations
- Investing.com may change its HTML layout, render the table dynamically, or restrict automated requests. The app reports failures instead of inventing values.
- The tested series is MSCI World Net USD (`MIWO00000NUS`). It is not automatically the correct benchmark for any of the five AIA funds. Match exact index variant and currency before assigning a return to a fund.
- Publicly viewable data may have terms governing automated access, reuse, and redistribution. Check the source terms before expanding use.
- Benchmark parsing is best-effort; validate the extracted wording against each source PDF.
