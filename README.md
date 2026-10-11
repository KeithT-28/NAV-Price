# NAV price — AIA Factsheet Finder & Extractor

This version is designed to discover AIA ILP fund pages from the official directory and, if needed, AIA sitemaps. It then finds official factsheet PDF links and extracts benchmark wording, document-date candidates and reported performance-table candidates.

## What's new
- Tries AIA's fund-price directory first, then sitemap discovery if needed.
- Does not present a short hard-coded list as the complete 41-fund catalogue.
- Includes an optional bulk scan of every fund page discovered, with CSV export.
- Shows a per-fund status when a PDF is not found or cannot be parsed.
- Keeps manual PDF upload as a fallback.

## Deploy
1. In your GitHub `nav-price` repository, replace `app.py`, `requirements.txt`, and `README.md` with these files.
2. Commit the changes.
3. In Streamlit Community Cloud, wait for the app to redeploy. If needed, use **Refresh AIA catalogue and pages** in the sidebar.
4. Check the discovered fund count. The target is all 41 funds; if fewer are discovered, open **Directory discovery diagnostics** and share the displayed message so the discovery method can be adjusted.
5. Try one fund first, then use **Scan discovered funds** to test the full catalogue. Download the CSV to review which funds succeeded.

## Important
The app extracts candidate text from PDFs; it does not guarantee exact table alignment or that every figure is correct. Verify benchmark notes and returns against the original official factsheet. It never fills missing figures with estimates.

Official sources:
- https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-fund-price
- https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/fund-performance
- https://www.aia.com.sg/en/our-products/save-and-invest/aia-funds-information/aia-annual-funds-reports
