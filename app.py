import streamlit as st
import pandas as pd
import plotly.express as px

from scraper import scrape_url, parse_html_bytes, firecrawl_available
from processor import compute_tfidf
from translator import has_non_english, translate_terms

st.set_page_config(
    page_title="TF-IDF Competitor Analysis",
    page_icon="🔍",
    layout="wide",
)

st.title("TF-IDF Competitor Analysis")

with st.sidebar:
    st.header("Settings")

    presence_pct = st.slider(
        "Min. competitor presence (%)",
        min_value=10, max_value=80, value=20, step=5,
        help="Only show terms found on at least this % of competitor pages. Lower = more terms shown.",
    )

    custom_sw = st.text_input(
        "Extra stopwords to exclude (comma-separated)",
        placeholder="e.g. brand, cityname, promo",
    )

    top_n = st.slider("Max unigrams to show (bigrams ≈ 60 %, trigrams ≈ 30 %)", 10, 100, 50, step=10)

    st.markdown("---")
    st.subheader("Scraping")
    fc_available = firecrawl_available()
    if fc_available:
        use_firecrawl = st.toggle("Use Firecrawl", value=True,
            help="Firecrawl handles JS-heavy and blocked sites better. Disable to use basic HTTP scraping.")
    else:
        use_firecrawl = False
        st.caption("Firecrawl not configured. Using basic HTTP scraping.")

    st.markdown("---")
    st.caption(
        "Red rows = competitors mention this term more than you.  \n"
        "Green rows = you mention this term more than competitors."
    )

mode = st.radio(
    "How do you want to provide page content?",
    ["Scrape from URLs", "Paste text content", "Upload HTML files"],
    horizontal=True,
)

st.markdown("---")

scraped = []
my_url = "my_page"
run = False

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
    )
    run = st.button("Run Analysis", type="primary", use_container_width=True)

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
            scraped.append(scrape_url(url, use_firecrawl=use_firecrawl))
            progress.progress((idx + 1) / len(all_urls))
        progress.empty()
        status.empty()

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
            key=f"comp_text_{i}",
        )
        comp_texts.append(txt)

    run = st.button("Run Analysis", type="primary", use_container_width=True)

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

else:
    st.markdown(
        "**How to save HTML files from Chrome:**  \n"
        "Open the page → press `Ctrl+S` → choose **Webpage, HTML Only** → save.  \n"
        "Do this for your page and each competitor, then upload all files below."
    )
    my_file = st.file_uploader("Your page HTML file", type=["html", "htm"])
    comp_files = st.file_uploader(
        "Competitor HTML files (up to 10)", type=["html", "htm"], accept_multiple_files=True
    )
    run = st.button("Run Analysis", type="primary", use_container_width=True)

    if run:
        if not my_file:
            st.error("Please upload your page HTML file.")
            st.stop()
        if not comp_files:
            st.error("Please upload at least one competitor HTML file.")
            st.stop()

        my_url = my_file.name
        my_result = parse_html_bytes(my_file.read(), url=my_file.name)
        scraped = [my_result]

        for f in comp_files[:10]:
            scraped.append(parse_html_bytes(f.read(), url=f.name))

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

    with st.spinner("Detecting languages…"):
        non_english = has_non_english(scraped)

    if non_english:
        with st.spinner("Translating non-English terms…"):
            translations = translate_terms(df["Keyword / Phrase"].tolist())
            df.insert(1, "English Translation", df["Keyword / Phrase"].map(translations))

    st.session_state["df"] = df
    st.session_state["my_url"] = my_url
    st.session_state["scraped"] = scraped

if "df" in st.session_state:
    df = st.session_state["df"]
    my_url = st.session_state["my_url"]

    st.markdown("---")

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

    tab1, tab2, tab3 = st.tabs(["Full Results", "Gap Analysis", "Chart"])

    def clean(frame):
        return frame.drop(columns=["_opportunity"], errors="ignore").copy()

    fmt = {
        "Avg Mentions (Competitors)": "{:.1f}",
        "% Competitors Using": "{:.1f}%",
    }

    def _color_row(row):
        if row.get("Mentions (My Page)", 0) < row.get("Avg Mentions (Competitors)", 0):
            return ["background-color: #ffe0e0"] * len(row)
        if row.get("Mentions (My Page)", 0) > row.get("Avg Mentions (Competitors)", 0):
            return ["background-color: #d4edda"] * len(row)
        return [""] * len(row)

    with tab1:
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
            st.dataframe(styled, use_container_width=True, height=min(520, len(sub) * 35 + 60))

        csv = clean(df).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="tfidf_analysis.csv",
            mime="text/csv",
        )

    with tab2:
        st.subheader("Missing terms — not found on your page at all")
        missing = clean(df[df["Found In My Page"] == "No"])
        if missing.empty:
            st.success("No gaps — your page covers all high-frequency competitor terms.")
        else:
            st.dataframe(
                missing.style.apply(_color_row, axis=1).format(fmt),
                use_container_width=True, height=400,
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
                use_container_width=True, height=350,
            )

    with tab3:
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
        st.plotly_chart(fig, use_container_width=True)
