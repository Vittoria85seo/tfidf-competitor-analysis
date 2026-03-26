# TF-IDF Competitor Analysis Tool

## Overview

A Streamlit web application with two SEO analysis tools:
1. **TF-IDF Competitor Analysis** — Compares on-page content using TF-IDF to identify keyword gaps and content opportunities.
2. **Keyword Optimizer** — Page Optimizer Pro-style analysis comparing exact match keyword and variation counts per HTML element against weighted competitor averages.

## Project Structure

### Python Application (root level)
- `app.py` — Streamlit UI with tool selector, inputs, sidebar settings, results display with tabs
- `keyword_analyzer.py` — Keyword Optimizer engine: per-element keyword counting, POP-calibrated scaling, outlier detection
- `scraper.py` — URL fetching with Firecrawl (primary), static + fallback, HTML parsing
- `processor.py` — TF-IDF computation using scikit-learn
- `translator.py` — Language detection and translation
- `product_detector.py` — Product listing detection from HTML
- `requirements.txt` — Python dependencies

### Monorepo Infrastructure
- `artifacts/api-server/` — Express 5 API server (shared backend)
- `artifacts/tfidf-tool/` — Streamlit app artifact config (routes "/" to Streamlit on port 5000)
- `lib/` — Shared TypeScript libraries (api-spec, api-zod, api-client-react, db)

## Tech Stack

- **Frontend**: Streamlit (port 5000)
- **Scraping**: Firecrawl API (primary), requests + BeautifulSoup4 + lxml (fallback)
- **TF-IDF**: scikit-learn TfidfVectorizer + CountVectorizer
- **Text processing**: NLTK (multi-language stopwords)
- **Language detection**: langdetect
- **Translation**: deep-translator (Google Translate)
- **Data**: pandas
- **Charts**: Plotly

## Secrets

- `FIRECRAWL_API_KEY` — Firecrawl API key for primary scraping

## Run Command

```
streamlit run app.py --server.port 5000
```
