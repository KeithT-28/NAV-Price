# NAV price — AIA Singapore ILP Fund Monitor

A Streamlit app for monitoring AIA Singapore ILP fund pages, published NAV/unit prices, previous available valuation-day returns, and publicly disclosed underlying investments.

## Features

- Discovers AIA ILP fund pages from the official fund-price directory, with a small fallback list if links are not present in the returned HTML.
- Retrieves fund facts and links to official fund documents where the public HTML exposes them.
- Calculates returns from the two most recent prices detected in a historical price table.
- Exports the monitor to CSV.
- Includes a CSV import tool for official price history if the AIA website's interactive price table is not available to a simple web request.
- Does not invent missing prices or holdings.

## Deploy on GitHub + Streamlit Community Cloud

1. Create a **private** GitHub repository named `nav-price` (or another name you prefer).
2. Upload `app.py`, `requirements.txt`, and `README.md` to the repository root.
3. Commit the files to the `main` branch.
4. Open Streamlit Community Cloud and create a new app from that repository.
5. Select `app.py` as the main file and deploy.
6. Open the app on your computer or iPhone. The layout is responsive.

## Important data limitations

AIA's public pages use interactive components for some price charts and historical tables. These values may be loaded client-side and may not be present in the HTML returned to Streamlit. The app only calculates returns when it can read at least two published prices. If values are missing, it leaves them blank and offers CSV import rather than substituting estimated data.

The app attempts to discover the full live fund directory, but if AIA changes its page structure or blocks requests, it may only show the fallback fund list. Check the discovered fund count against AIA's official directory.

Underlying funds are not the same as security-level holdings. For a complete stock/bond look-through, use the linked official factsheets and reports where available.

## Official sources

- AIA ILP Fund Prices: https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price
- AIA Fund Information: https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information
- AIA ILP Fund Tools: https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-ilp-fund-tools
- AIA Annual Funds Reports: https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-annual-funds-reports

## Run locally (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```
