# Real Exchange Rate Explorer (IMF data)

A Streamlit app that computes and plots the **real exchange rate (RER)** between any two IMF member countries (or the Euro area) using monthly IMF CPI and exchange-rate data from January 1976, where available.

Compatible with **Python 3.12**.

## Economics

- **S(t)** = units of Country 2 currency per one unit of Country 1 currency.
  IMF exchange rates are quoted as local currency per USD, so
  `S(t) = (Country 2 per USD) / (Country 1 per USD)`.
- **P1(t), P2(t)** = monthly CPI index for Country 1 and Country 2.
- **RER(t) = S(t) × P1(t) / P2(t)**
- **RER\*** = average of RER(t) over valid months in the user-selected start and end months (recomputed whenever the dates change).
- **Real Index(t) = 100 × RER(t) / RER\***
- The nominal series S(t) is always plotted in actual currency units (never normalized).

A month is *valid* only if S, P1, and P2 are all available for that month.

## Features

- Country 1 and Country 2 selectors (IMF countries + Euro area, code `G163`)
- Start/end month slider that limits choices to months with complete data
- Interactive Plotly chart: **Real**, **Nominal**, or **Both** (Both uses separate y-axes)
- CSV download of every observation and calculation in the selected sample
- Purple theme with a Kellogg logo banner

## Data sources (IMF SDMX 3.0)

Base URL: `https://api.imf.org/external/sdmx/3.0`

| Series | Dataflow | Key |
|---|---|---|
| CPI | `IMF.STA/CPI` | `{ISO3}.CPI._T.IX.M` |
| Exchange rate (local currency per USD) | `IMF.STA/ER` | `{ISO3}.XDC_USD.PA_RT.M` |

The Euro area uses the code `G163`. Coverage varies; if a series is missing or the two countries do not overlap, the app tells you instead of failing. Responses are cached for 12 hours.

## Kellogg logo

The official Northwestern Kellogg logo is a trademark and is not bundled in this repository. To show it:

1. Obtain the approved logo from Northwestern/Kellogg's brand resources (and confirm you are permitted to use it).
2. Save it as `assets/kellogg_logo.png` (`.svg`, `.jpg`, `.jpeg`, `.webp` also work).
3. Commit it with the rest of the repo.

The logo is shown on a white card so it stays legible on the purple background. Without the file, a text banner appears instead.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, `README.md` (and `assets/kellogg_logo.png`) to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io) and choose **Create app**.
3. Select the repository, branch, and `app.py` as the main file.
4. Under **Advanced settings**, choose **Python 3.12**, then deploy.

## Notes and limitations

- IMF series can have gaps, start late, or be discontinued; these months are excluded from RER\* and the charts.
- Euro-area members' national series switch to euro-denominated values at adoption; for long-run comparisons the Euro area aggregate (`G163`) is usually more consistent.
- Hyperinflation or very large devaluation episodes can make the Real Index scale hard to read; narrow the sample if needed.
- This tool is for education and research and is not financial advice.
