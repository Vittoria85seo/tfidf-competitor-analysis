import re
import os
import json
import time
import streamlit as st
import pandas as pd
import plotly.express as px
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from scraper import scrape_url, parse_html_bytes, firecrawl_available
from processor import compute_tfidf
from translator import has_non_english, translate_terms, SUPPORTED_LANGUAGES
from product_detector import analyze_multiple_pages

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".html_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _save_html_cache(my_url, my_html, comp_data, input_mode="html"):
    data = {"my_url": my_url, "my_html": my_html, "competitors": comp_data, "input_mode": input_mode}
    with open(os.path.join(CACHE_DIR, "html_cache.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    st.session_state.pop("html_cache_data", None)


def _load_html_cache():
    if "html_cache_data" in st.session_state:
        return st.session_state["html_cache_data"]
    path = os.path.join(CACHE_DIR, "html_cache.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        st.session_state["html_cache_data"] = data
        return data
    except Exception:
        return None


st.set_page_config(
    page_title="TF-IDF Competitor Analysis",
    page_icon="🔍",
    layout="wide",
)

if "_app_initialized" not in st.session_state:
    st.session_state["_app_initialized"] = True
    cache_path = os.path.join(CACHE_DIR, "html_cache.json")
    if os.path.exists(cache_path):
        os.remove(cache_path)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

    :root {
        --bg: #fafbfe;
        --surface: #ffffff;
        --border: #e8ecf4;
        --border-hover: #c7d0e0;
        --text-primary: #1a1f36;
        --text-secondary: #525f7f;
        --text-muted: #8792a2;
        --accent: #635bff;
        --accent-hover: #5046e5;
        --accent-light: #f0eeff;
        --accent-glow: rgba(99,91,255,0.12);
        --radius: 10px;
        --radius-lg: 14px;
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.03);
        --shadow-md: 0 2px 4px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
        --shadow-lg: 0 4px 8px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06);
    }

    .stApp {
        font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        background: var(--bg) !important;
        color: var(--text-primary);
    }
    .stApp > header { background: transparent !important; }
    .block-container { max-width: 1100px; padding-top: 2rem !important; }

    section[data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
        box-shadow: 1px 0 8px rgba(0,0,0,0.02) !important;
    }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stTextInput label,
    section[data-testid="stSidebar"] .stTextArea label,
    section[data-testid="stSidebar"] .stSlider label {
        font-size: 0.8rem !important;
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: var(--border) !important;
    }
    .sidebar-section-title {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--accent) !important;
        margin-bottom: 0.6rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea,
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        border-radius: 8px !important;
        border-color: var(--border) !important;
    }
    section[data-testid="stSidebar"] details[data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        background: var(--bg) !important;
    }

    .main-header {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 1.6rem 2rem;
        margin-bottom: 1.5rem;
        box-shadow: var(--shadow-sm);
        display: flex;
        align-items: center;
        gap: 1.2rem;
    }
    .main-header-icon {
        width: 48px; height: 48px;
        border-radius: 12px;
        background: var(--accent);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 2px 8px var(--accent-glow);
    }
    .main-header-icon svg { width: 24px; height: 24px; }
    .main-header-text h1 {
        color: var(--text-primary) !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        letter-spacing: -0.02em;
        line-height: 1.3;
    }
    .main-header-text p {
        color: var(--text-muted) !important;
        font-size: 0.85rem !important;
        margin: 0.15rem 0 0 0 !important;
        font-weight: 400;
    }

    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 1.1rem 1.3rem;
        box-shadow: var(--shadow-sm);
        transition: box-shadow 0.15s ease;
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: var(--shadow-md);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.72rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.7rem !important;
        font-weight: 700 !important;
        color: var(--text-primary) !important;
    }

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: var(--accent) !important;
        border: none !important;
        border-radius: var(--radius) !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        padding: 0.6rem 1.4rem !important;
        color: white !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 1px 3px rgba(99,91,255,0.2), 0 2px 8px rgba(99,91,255,0.12) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 2px 4px rgba(99,91,255,0.2), 0 4px 14px rgba(99,91,255,0.18) !important;
        transform: translateY(-1px) !important;
    }
    .stMainBlockContainer button[kind="secondary"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        background: var(--surface) !important;
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
        transition: all 0.15s ease !important;
    }
    .stMainBlockContainer button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
        background: var(--accent-light) !important;
    }

    .stMainBlockContainer input[type="text"],
    .stMainBlockContainer textarea {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--text-primary) !important;
        font-size: 0.88rem !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stMainBlockContainer input[type="text"]:focus,
    .stMainBlockContainer textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-glow) !important;
    }

    details[data-testid="stExpander"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-lg) !important;
        box-shadow: var(--shadow-sm) !important;
    }
    details[data-testid="stExpander"] summary {
        font-weight: 600;
        font-size: 0.86rem;
        color: var(--text-secondary);
    }

    div[data-testid="stDataFrame"] {
        border-radius: var(--radius-lg);
        overflow: hidden;
        border: 1px solid var(--border);
        box-shadow: var(--shadow-sm);
    }

    div[data-testid="stAlert"] {
        border-radius: var(--radius) !important;
    }

    hr {
        border: none;
        border-top: 1px solid var(--border);
        margin: 1.2rem 0;
    }

    .stMainBlockContainer .stSelectbox > div > div {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
    }
    .stMainBlockContainer .stNumberInput input {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
    }

    .stSpinner > div { color: var(--accent) !important; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 4px !important;
        background: var(--bg);
        border-radius: var(--radius);
        border: 1px solid var(--border);
        padding: 4px;
    }
    .stTabs [data-baseweb="tab-list"] button {
        border-radius: 7px !important;
        font-weight: 500 !important;
        font-size: 0.84rem !important;
        color: var(--text-muted) !important;
        padding: 0.5rem 1.2rem !important;
        border: none !important;
        background: transparent !important;
        white-space: nowrap !important;
    }
    .stTabs [data-baseweb="tab-list"] button:hover {
        color: var(--text-secondary) !important;
        background: var(--surface) !important;
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        background: var(--accent) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 4px rgba(99,91,255,0.25) !important;
    }
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    section[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] [role="slider"] {
        background: var(--accent) !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <div class="main-header-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
    </div>
    <div class="main-header-text">
        <h1>TF-IDF Competitor Analysis</h1>
        <p>Content gap analysis — find what terms your competitors use that you don't</p>
    </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sidebar-section-title">Settings</div>', unsafe_allow_html=True)

    st.caption("**Scraping**")
    fc_available = firecrawl_available()
    if fc_available:
        use_firecrawl = st.toggle("Use Firecrawl", value=True,
            help="Firecrawl handles JS-heavy and blocked sites better. Disable to use basic HTTP scraping.")
    else:
        use_firecrawl = False
        st.caption("Firecrawl not configured. Using basic HTTP scraping.")

    st.markdown("---")
    st.caption("**TF-IDF**")

    presence_pct = st.slider(
        "Min. competitor presence (%)",
        min_value=10, max_value=80, value=30, step=5,
        help="Only show terms found on at least this % of competitor pages. Lower = more terms shown.",
    )

    custom_sw = st.text_input(
        "Extra stopwords to exclude (comma-separated)",
        placeholder="e.g. brand, cityname, promo",
    )

    top_n = st.slider("Max unigrams to show (bigrams ≈ 60 %, trigrams ≈ 30 %)", 10, 200, 80, step=10)

    st.markdown("---")
    st.caption("**Translation**")
    source_lang_label = st.selectbox(
        "Content language",
        options=list(SUPPORTED_LANGUAGES.keys()),
        index=0,
        help="Select the language of the pages you're analysing. This improves translation accuracy — auto-detect can misidentify single words.",
    )
    source_lang = SUPPORTED_LANGUAGES[source_lang_label]

    st.markdown("---")
    st.caption(
        "Green rows = opportunity — competitors use this term more than you.  \n"
        "Red rows = you already mention this term more than competitors."
    )

if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0
rc = st.session_state["reset_counter"]

scraped = []
my_url = "my_page"
run = False

has_results = "df" in st.session_state

if not has_results:
    _mode_options = ["Scrape from URLs", "Paste text content", "Paste HTML source"]
    cached_check = _load_html_cache()
    _mode_default = 0
    if cached_check and cached_check.get("my_html"):
        _mode_default = 2
    mode = st.radio(
        "How do you want to provide page content?",
        _mode_options,
        index=_mode_default,
        horizontal=True,
        label_visibility="visible",
    )
else:
    mode = None

if mode == "Scrape from URLs":
    st.markdown("Paste all URLs below — **first line = your URL**, remaining lines = competitors.")
    url_input = st.text_area(
        "URLs (one per line)",
        height=200,
        placeholder=(
            "https://yoursite.com/page\n"
            "https://competitor1.com/page\n"
            "https://competitor2.com/page\n"
            "..."
        ),
        key=f"url_input_{rc}",
    )
    run = st.button("Run Analysis", type="primary", width='stretch')

    if run:
        urls = [u.strip() for u in url_input.strip().splitlines() if u.strip()]
        if len(urls) < 2:
            st.error("Please enter at least 2 URLs (your URL + at least 1 competitor).")
            st.stop()

        my_url = urls[0]
        all_urls = [my_url] + urls[1:11]

        progress = st.progress(0)
        status = st.empty()
        for idx, url in enumerate(all_urls):
            label = "Your page" if idx == 0 else f"Competitor {idx}"
            status.text(f"Fetching {label}: {url}")
            try:
                scraped.append(scrape_url(url, use_firecrawl=use_firecrawl))
            except Exception as e:
                scraped.append({
                    "meta_title": "", "meta_description": "", "headings": "",
                    "body": "", "combined": "", "word_count": 0,
                    "url": url, "error": str(e), "method": "none",
                })
            progress.progress((idx + 1) / len(all_urls))
            if use_firecrawl and idx < len(all_urls) - 1:
                time.sleep(2)
        progress.empty()
        status.empty()

        ok_scraped = [d for d in scraped if not d["error"] and d.get("_raw_html")]
        if ok_scraped:
            my_raw = ok_scraped[0].get("_raw_html", b"")
            comp_raw = [{"url": d["url"], "html": d["_raw_html"].decode("utf-8", errors="replace")} for d in ok_scraped[1:]]
            _save_html_cache(my_url, my_raw.decode("utf-8", errors="replace"), comp_raw, input_mode="scrape")

        with st.expander("Scraping details"):
            for idx, d in enumerate(scraped):
                label = "YOUR PAGE" if d["url"] == my_url else f"Competitor {idx}"
                if d["error"]:
                    st.error(f"{label}: {d['url']} — FAILED: {d['error']}")
                elif d.get("word_count", 0) < 50:
                    st.warning(f"{label}: {d['url']} — site may be blocking scraping, try uploading HTML or pasting text instead")
                else:
                    st.success(f"{label}: {d['url']} — OK")
                if d.get("redirect_warning"):
                    st.warning(f"⚠ {d['redirect_warning']}")

elif mode == "Paste text content":
    st.markdown(
        "Paste the **text content** from each page below. "
        "Copy the visible text from the page (select all → copy) and paste it into each box."
    )
    my_text = st.text_area(
        "Your page text",
        height=150,
        placeholder="Paste the full text content from your page here...",
        key=f"my_text_{rc}",
    )

    st.markdown("**Competitor pages** — add text for each competitor (up to 10):")
    num_competitors = st.number_input(
        "Number of competitors", min_value=1, max_value=10, value=3, step=1
    )
    comp_texts = []
    for i in range(int(num_competitors)):
        txt = st.text_area(
            f"Competitor {i + 1} text",
            height=120,
            placeholder=f"Paste text from competitor {i + 1} here...",
            key=f"comp_text_{i}_{rc}",
        )
        comp_texts.append(txt)

    run = st.button("Run Analysis", type="primary", width='stretch')

    if run:
        if not my_text.strip():
            st.error("Please paste your page text content.")
            st.stop()

        valid_comps = [t for t in comp_texts if t.strip()]
        if not valid_comps:
            st.error("Please paste at least one competitor's text content.")
            st.stop()

        my_url = "my_page"
        scraped = [{
            "url": my_url,
            "meta_title": "",
            "meta_description": "",
            "headings": "",
            "body": my_text.strip(),
            "combined": my_text.strip(),
            "word_count": len(my_text.strip().split()),
            "error": None,
        }]

        for i, txt in enumerate(valid_comps):
            scraped.append({
                "url": f"competitor_{i + 1}",
                "meta_title": "",
                "meta_description": "",
                "headings": "",
                "body": txt.strip(),
                "combined": txt.strip(),
                "word_count": len(txt.strip().split()),
                "error": None,
            })

        with st.expander("Input details"):
            for d in scraped:
                label = "YOUR PAGE" if d["url"] == my_url else f"Competitor: {d['url']}"
                wc = d.get("word_count", 0)
                if wc < 50:
                    st.warning(f"{label} — only {wc} words (may produce limited results)")
                else:
                    st.success(f"{label} — {wc} words")

elif mode == "Paste HTML source":
    cached = _load_html_cache()
    use_cached = False

    if cached and cached.get("my_html"):
        n_comps = len(cached.get("competitors", []))
        if n_comps > 0:
            st.success(f"Saved HTML codes found: **{cached['my_url']}** + **{n_comps} competitors**")
        else:
            st.warning(f"Saved target page: **{cached['my_url']}** — no competitors saved. Add at least one below or clear and start fresh.")

        with st.expander("Manage saved pages", expanded=False):
            st.write(f"**Your page:** {cached['my_url']} ({len(cached['my_html']):,} chars)")
            for ci, cc in enumerate(cached["competitors"]):
                col_info, col_del = st.columns([5, 1])
                col_info.write(f"**Comp {ci+1}:** {cc['url']} ({len(cc['html']):,} chars)")
                if col_del.button("🗑️", key=f"del_comp_{ci}", help=f"Remove competitor {ci+1}"):
                    cached["competitors"].pop(ci)
                    _save_html_cache(cached["my_url"], cached["my_html"], cached["competitors"])
                    st.rerun()

            if cached["competitors"]:
                st.markdown("---")
                st.markdown("**Replace a competitor**")
                replace_idx = st.selectbox(
                    "Select competitor to replace",
                    options=list(range(len(cached["competitors"]))),
                    format_func=lambda i: f"Comp {i+1}: {cached['competitors'][i]['url']}",
                    key="replace_comp_idx",
                )
                replace_url = st.text_input("New URL", key="replace_comp_url", placeholder="https://competitor.com/page")
                replace_html = st.text_area("New HTML source", key="replace_comp_html", height=100, placeholder="Paste HTML source...")
                if st.button("Replace competitor", key="replace_comp_btn"):
                    if replace_url.strip() and replace_html.strip():
                        cached["competitors"][replace_idx] = {"url": replace_url.strip(), "html": replace_html.strip()}
                        _save_html_cache(cached["my_url"], cached["my_html"], cached["competitors"])
                        st.success(f"Replaced competitor {replace_idx+1} with {replace_url.strip()}")
                        st.rerun()
                    else:
                        st.warning("Enter both URL and HTML source to replace.")

            st.markdown("---")
            st.markdown("**Add a competitor**")
            if len(cached["competitors"]) >= 10:
                st.info("Maximum of 10 competitors reached.")
            else:
                add_url = st.text_input("URL", key="add_comp_url", placeholder="https://newcompetitor.com/page")
                add_html = st.text_area("HTML source", key="add_comp_html", height=100, placeholder="Paste HTML source...")
                if st.button("Add competitor", key="add_comp_btn"):
                    if add_url.strip() and add_html.strip():
                        cached["competitors"].append({"url": add_url.strip(), "html": add_html.strip()})
                        _save_html_cache(cached["my_url"], cached["my_html"], cached["competitors"])
                        st.success(f"Added competitor: {add_url.strip()}")
                        st.rerun()
                    else:
                        st.warning("Enter both URL and HTML source to add.")

            st.markdown("---")
            if st.button("🗑️ Clear all saved codes (start fresh)", type="secondary", key="clear_cache_btn"):
                cache_path = os.path.join(CACHE_DIR, "html_cache.json")
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                st.rerun()

        if n_comps > 0:
            use_cached_btn = st.button("Run Analysis with saved codes", type="primary", width='stretch')
            if use_cached_btn:
                use_cached = True
                run = True

        st.markdown("---")
        st.caption("Or paste new codes below to replace all saved ones:")

    st.markdown(
        "**How to get HTML source from Chrome:**  \n"
        "Open the page → right-click → **View Page Source** → select all (`Ctrl+A`) → copy (`Ctrl+C`).  \n"
        "Paste the HTML source code into the boxes below."
    )

    my_html_url = st.text_input(
        "Your page URL",
        placeholder="https://yoursite.com/page",
        key=f"html_my_url_{rc}",
    )
    my_html_src = ""
    if my_html_url.strip():
        my_html_src = st.text_area(
            f"HTML source for your page",
            height=150,
            placeholder="Paste the full HTML source code here...",
            key=f"html_my_src_{rc}",
        )

    comp_url_input = st.text_area(
        "Competitor URLs (one per line, up to 10)",
        height=120,
        placeholder=(
            "https://competitor1.com/page\n"
            "https://competitor2.com/page\n"
            "..."
        ),
        key=f"html_comp_urls_{rc}",
    )
    comp_html_sources = []
    comp_urls_list = [u.strip() for u in comp_url_input.strip().splitlines() if u.strip()][:10]
    for i, curl in enumerate(comp_urls_list):
        st.caption(f"Competitor {i+1}: {curl}")
        src = st.text_area(
            f"HTML source for competitor {i+1}",
            height=150,
            placeholder=f"Paste HTML source here...",
            key=f"html_comp_src_{i}_{rc}",
            label_visibility="collapsed",
        )
        comp_html_sources.append((curl, src))

    if not use_cached:
        run = st.button("Run Analysis", type="primary", width='stretch')

    if use_cached and cached:
        my_url = cached["my_url"]
        my_html_bytes = cached["my_html"].encode("utf-8")
        my_result = parse_html_bytes(my_html_bytes, url=my_url)
        my_result["_raw_html"] = my_html_bytes
        scraped = [my_result]

        for cc in cached["competitors"]:
            comp_html_bytes = cc["html"].encode("utf-8")
            comp_result = parse_html_bytes(comp_html_bytes, url=cc["url"])
            comp_result["_raw_html"] = comp_html_bytes
            scraped.append(comp_result)
    elif run:
        if not my_html_url.strip():
            st.error("Please enter your page URL.")
            st.stop()
        if not my_html_src.strip():
            st.error("Please paste the HTML source for your page.")
            st.stop()
        valid_comps = [(u, s) for u, s in comp_html_sources if s.strip()]
        if not valid_comps:
            st.error("Please paste HTML source for at least one competitor.")
            st.stop()

        _save_html_cache(
            my_html_url.strip(),
            my_html_src.strip(),
            [{"url": u, "html": s.strip()} for u, s in valid_comps],
        )

        my_url = my_html_url.strip()
        my_html_bytes = my_html_src.strip().encode("utf-8")
        my_result = parse_html_bytes(my_html_bytes, url=my_url)
        my_result["_raw_html"] = my_html_bytes
        scraped = [my_result]

        for curl, csrc in valid_comps:
            comp_html_bytes = csrc.strip().encode("utf-8")
            comp_result = parse_html_bytes(comp_html_bytes, url=curl)
            comp_result["_raw_html"] = comp_html_bytes
            scraped.append(comp_result)

        with st.expander("Parsing details"):
            for d in scraped:
                label = "YOUR PAGE" if d["url"] == my_url else f"Competitor: {d['url']}"
                wc = d.get("word_count", 0)
                if d["error"]:
                    st.error(f"{label} — ERROR: {d['error']}")
                elif wc < 50:
                    st.warning(f"{label} — only {wc} words found")
                else:
                    st.success(f"{label} — {wc} words parsed")
                if d["url"] == my_url and d.get("body"):
                    st.caption("Body preview (first 300 chars):")
                    st.code(d["body"][:300])

if run and scraped:
    custom_words = [w.strip() for w in custom_sw.split(",") if w.strip()] if custom_sw else None
    with st.spinner("Computing TF-IDF scores…"):
        try:
            df = compute_tfidf(
                scraped,
                my_url=my_url,
                presence_threshold=presence_pct / 100,
                custom_stopwords=custom_words,
            )
        except ValueError as e:
            st.error(str(e))
            st.stop()

    if df.empty:
        st.warning(
            "No terms passed the filters. "
            "Try lowering the competitor presence slider or check the parsing details above."
        )
        st.stop()

    n_bi = max(top_n * 3 // 5, 10)
    n_tri = max(top_n * 3 // 10, 5)
    df = pd.concat([
        df[df["N-gram Type"] == "Unigram"].head(top_n),
        df[df["N-gram Type"] == "Bigram"].head(n_bi),
        df[df["N-gram Type"] == "Trigram"].head(n_tri),
    ]).reset_index(drop=True)

    needs_translation = source_lang != "en"
    if source_lang == "auto":
        with st.spinner("Detecting languages…"):
            needs_translation = has_non_english(scraped)

    if needs_translation:
        with st.spinner("Translating terms to English…"):
            translations = translate_terms(df["Keyword / Phrase"].tolist(), source_lang=source_lang)
            df.insert(1, "English Translation", df["Keyword / Phrase"].map(translations))

    st.session_state["df"] = df
    st.session_state["my_url"] = my_url
    st.session_state["scraped"] = scraped

if "df" in st.session_state:
    df = st.session_state["df"]
    my_url = st.session_state["my_url"]

    if st.button("⟵ New Analysis", type="secondary"):
        st.session_state["reset_counter"] = st.session_state.get("reset_counter", 0) + 1
        for key in list(st.session_state.keys()):
            if key != "reset_counter":
                del st.session_state[key]
        st.rerun()

    n_missing = int((df["Found In My Page"] == "No").sum())
    n_underused = int(
        ((df["Found In My Page"] == "Yes") &
        (df["Avg Mentions (Competitors)"] > df["Mentions (My Page)"])).sum()
    )
    n_strong = int(
        (df["Mentions (My Page)"] >= df["Avg Mentions (Competitors)"]).sum()
    )
    n_total = len(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Terms analysed", n_total)
    c2.metric("Missing from your page", n_missing)
    c3.metric("Underused vs competitors", n_underused)
    c4.metric("You outperform competitors", n_strong)

    def clean(frame):
        return frame.drop(columns=["_opportunity"], errors="ignore").copy()

    fmt = {
        "Avg Mentions (Competitors)": "{:.1f}",
        "% Competitors Using": "{:.1f}%",
    }

    def _color_row(row):
        if row.get("Mentions (My Page)", 0) < row.get("Avg Mentions (Competitors)", 0):
            return ["background-color: #d4edda"] * len(row)
        if row.get("Mentions (My Page)", 0) > row.get("Avg Mentions (Competitors)", 0):
            return ["background-color: #ffe0e0"] * len(row)
        return [""] * len(row)

    tfidf_sub_tabs = st.tabs(["Full Results", "Gap Analysis", "Chart", "Product Listings"])

    with tfidf_sub_tabs[0]:
        for section_label, ng_type in [
            ("Single words (unigrams)", "Unigram"),
            ("2-word phrases (bigrams)", "Bigram"),
            ("3-word phrases (trigrams)", "Trigram"),
        ]:
            sub = clean(df[df["N-gram Type"] == ng_type])
            if sub.empty:
                continue
            st.subheader(section_label)
            styled = sub.style.apply(_color_row, axis=1).format(fmt)
            st.dataframe(styled, width='stretch', height=min(520, len(sub) * 35 + 60))

        csv = clean(df).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="tfidf_analysis.csv",
            mime="text/csv",
        )

    with tfidf_sub_tabs[1]:
        st.subheader("Missing terms — not found on your page at all")
        missing = clean(df[df["Found In My Page"] == "No"])
        if missing.empty:
            st.success("No gaps — your page covers all high-frequency competitor terms.")
        else:
            st.dataframe(
                missing.style.apply(_color_row, axis=1).format(fmt),
                width='stretch', height=400,
            )

        st.subheader("Underused terms — present but mentioned less than competitors")
        underused = clean(df[
            (df["Found In My Page"] == "Yes") &
            (df["Avg Mentions (Competitors)"] > df["Mentions (My Page)"])
        ])
        if underused.empty:
            st.info("No underused terms found.")
        else:
            st.dataframe(
                underused.style.apply(_color_row, axis=1).format(fmt),
                width='stretch', height=350,
            )

    with tfidf_sub_tabs[2]:
        st.subheader("Top 20 terms by competitor usage")
        chart_df = df.head(20).copy()
        kw_col = "English Translation" if "English Translation" in chart_df.columns else "Keyword / Phrase"
        chart_df["label"] = chart_df.apply(
            lambda r: r[kw_col] if r.get(kw_col) else r["Keyword / Phrase"], axis=1
        ).str[:35]

        chart_long = chart_df[["label", "Mentions (My Page)", "Avg Mentions (Competitors)"]].melt(
            id_vars="label", var_name="Source", value_name="Mentions"
        )
        fig = px.bar(
            chart_long,
            x="Mentions",
            y="label",
            color="Source",
            orientation="h",
            barmode="group",
            color_discrete_map={
                "Mentions (My Page)": "#3498db",
                "Avg Mentions (Competitors)": "#e74c3c",
            },
            labels={"label": "Keyword", "Mentions": "Times mentioned"},
            title="Your page (blue) vs competitor average (red)",
        )
        fig.update_layout(yaxis={"autorange": "reversed"}, height=600, legend_title="")
        st.plotly_chart(fig, width='stretch')

    with tfidf_sub_tabs[3]:
        st.subheader("Product Listings Detection")
        st.markdown(
            "Detects product listings on each page. "
            "Useful for understanding how competitors structure their product pages."
        )
        scraped = st.session_state.get("scraped", [])
        pages_with_html = []
        for idx, d in enumerate(scraped):
            raw = d.get("_raw_html")
            if raw:
                label = d.get("url", f"Page {idx}")
                if idx == 0:
                    label = f"YOUR PAGE: {label}"
                else:
                    label = f"{idx}: {label}"
                html_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                pages_with_html.append({"label": label, "html": html_str})

        if not pages_with_html:
            st.warning("No HTML data available for product detection. This feature requires scraping from URLs or pasting HTML source.")
        else:
            with st.spinner("Detecting product listings…"):
                pl_results = analyze_multiple_pages(pages_with_html)

            def _short_url(full_url):
                from urllib.parse import urlparse
                if not full_url or not full_url.startswith("http"):
                    return full_url
                p = urlparse(full_url)
                domain = p.netloc.replace("www.", "")
                path = p.path.rstrip("/")
                if len(path) > 35:
                    path = "/…" + path[-30:]
                return domain + path

            def _short_page_label(label):
                import re
                m = re.match(r"(YOUR PAGE|\d+): (https?://\S+)", label)
                if m:
                    return f"{m.group(1)}: {_short_url(m.group(2))}"
                return label

            overview_rows = []
            for r in pl_results:
                page_type = r.get("page_type", "unknown")
                if page_type == "blog":
                    status = "Blog / Guide"
                elif page_type == "template":
                    status = "Unrendered template"
                elif r["product_count"] > 0:
                    status = f"{r['product_count']} products"
                else:
                    status = "Not detected"
                overview_rows.append({
                    "Page": _short_page_label(r["label"]),
                    "Page Type": status,
                    "Structure": r.get("structure", ""),
                })
            ov_df = pd.DataFrame(overview_rows)

            def _color_product_row(row):
                status = str(row.get("Page Type", ""))
                page = str(row.get("Page", ""))
                if page.startswith("YOUR PAGE"):
                    return ["background-color: #ede9fe"] * len(row)
                if "products" in status:
                    return ["background-color: #f3f0ff"] * len(row)
                elif status == "Not detected":
                    return ["background-color: #fef2f2"] * len(row)
                return [""] * len(row)

            styled_ov = ov_df.style.apply(_color_product_row, axis=1)
            st.dataframe(styled_ov, width='stretch', hide_index=True, height=min(420, len(ov_df) * 35 + 60))

            for r in pl_results:
                if r.get("product_count", 0) > 0 and r.get("products"):
                    short = _short_page_label(r["label"])
                    with st.expander(f"{short} — {r['product_count']} products"):
                        prod_rows = []
                        for p in r["products"]:
                            prod_rows.append({
                                "Product Name": p["name"],
                                "Price": p["price"],
                                "Image Alt Text": p["img_alt"],
                                "URL": p["url"],
                            })
                        st.dataframe(pd.DataFrame(prod_rows), width='stretch', hide_index=True, height=min(400, len(prod_rows) * 35 + 60))

            all_products = []
            for r in pl_results:
                for p in r.get("products", []):
                    all_products.append({
                        "Page": r["label"],
                        "Container Tag": r.get("container_tag", ""),
                        "Product Name": p["name"],
                        "Price": p["price"],
                        "Image Alt Text": p["img_alt"],
                        "URL": p["url"],
                    })
            if all_products:
                csv_data = pd.DataFrame(all_products).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Product Listings CSV",
                    data=csv_data,
                    file_name="product_listings.csv",
                    mime="text/csv",
                )
