# TF-IDF Competitor Analysis Tool

## Overview
A Streamlit web application that compares on-page content of your URL against up to 10 competitor URLs using TF-IDF analysis. Identifies keyword gaps, underused terms, and content opportunities for SEO.

## Project Structure
- `app.py` — Streamlit UI (inputs, sidebar settings, results display with tabs)
- `scraper.py` — URL fetching (`scrape_url`) with static + Playwright fallback, and HTML file parsing (`parse_html_bytes`)
- `processor.py` — TF-IDF computation (`compute_tfidf`) using scikit-learn, with unigram/bigram/trigram support
- `translator.py` — Language detection (`has_non_english`) via langdetect and translation (`translate_terms`) via deep-translator (Google Translate, free)
- `REQUIREMENTS.md` — Functional requirements document

## Tech Stack
- **Frontend**: Streamlit (port 5000)
- **Scraping**: Firecrawl API (primary), requests + BeautifulSoup4 + lxml (fallback), Playwright (JS fallback)
- **TF-IDF**: scikit-learn TfidfVectorizer + CountVectorizer
- **Text processing**: NLTK (multi-language stopwords)
- **Language detection**: langdetect
- **Translation**: deep-translator (Google Translate)
- **Data**: pandas
- **Charts**: Plotly

## Key Features
- Two input modes: URL scraping or HTML file upload
- Smart scraping with Playwright fallback for JS-heavy sites
- TF-IDF analysis with unigrams, bigrams, trigrams
- Configurable competitor presence threshold and custom stopwords
- Color-coded results (red = gap, green = advantage)
- Gap analysis tab (missing + underused terms)
- Bar chart comparison (top 20 terms)
- CSV export
- Auto language detection and translation

## Integrations
- **GitHub**: Connected via Replit connector (user: Vittoria85seo)

## Run Command
```
streamlit run app.py --server.port 5000
```
