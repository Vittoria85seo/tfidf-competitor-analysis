import re
import streamlit as st
import pandas as pd
import plotly.express as px
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from scraper import scrape_url, parse_html_bytes, firecrawl_available
from processor import compute_tfidf
from translator import has_non_english, translate_terms, SUPPORTED_LANGUAGES
from product_detector import analyze_multiple_pages


def _find_spaced_brand(domain_word, html_text):
    lower = domain_word.lower()
    for pattern in [
        r'title[=>][^<]*?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿa-zà-ÿ]+){1,5})',
        r'>([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿa-zà-ÿ]+){1,5})<',
    ]:
        for m in re.finditer(pattern, html_text):
            candidate = m.group(1).strip()
            if candidate.replace(" ", "").lower() == lower and " " in candidate:
                return candidate.title()
    return None


def _extract_site_name(filename, html_content):
    try:
        snippet = html_content[:60000] if isinstance(html_content, str) else html_content.decode("utf-8", errors="ignore")[:60000]
        soup = BeautifulSoup(snippet, "html.parser")

        og = soup.find("meta", property="og:site_name")
        if og and og.get("content", "").strip():
            return og["content"].strip()

        for tag in [soup.find("link", rel="canonical"), soup.find("meta", property="og:url")]:
            if tag:
                href = tag.get("href") or tag.get("content") or ""
                host = urlparse(href).hostname
                if host:
                    name_part = host.replace("www.", "").split(".")[0]
                    spaced = name_part.replace("-", " ").replace("_", " ")
                    return spaced.title()

        sep_match = re.search(r"[｜|–—]", filename)
        if sep_match:
            parts = re.split(r"[｜|–—]", filename)
            for p in reversed(parts):
                cleaned = re.sub(r"\(.*", "", p).strip().strip("_").strip()
                if 2 < len(cleaned) < 40 and not cleaned[0].isdigit():
                    return cleaned.replace("_", " ")

        domain_counts = {}
        skip = {"google", "facebook", "cdn", "cloudflare", "jquery", "bootstrap",
                "analytics", "doubleclick", "gstatic", "mozilla", "w3.org",
                "schema.org", "googleapis", "fontawesome", "unpkg", "jsdelivr",
                "cookiebot", "onetrust", "hotjar", "sentry", "segment", "twitter",
                "instagram", "youtube", "pinterest", "tiktok", "linkedin",
                "newrelic", "nr-data", "akamai", "fastly", "imgix", "shopify",
                "zendesk", "intercom", "crisp", "drift", "hubspot", "salesforce",
                "stripe", "paypal", "bing", "yahoo", "apple", "microsoft",
                "amazon", "cloudfront", "s3.amazonaws", "azureedge"}
        full_html = html_content if isinstance(html_content, str) else html_content.decode("utf-8", errors="ignore")
        for m in re.findall(r'https?://([a-zA-Z0-9.-]+\.[a-z]{2,})', full_html[:200000]):
            if not any(s in m.lower() for s in skip):
                domain_counts[m] = domain_counts.get(m, 0) + 1
        if domain_counts:
            top_domain = max(domain_counts, key=domain_counts.get)
            host = top_domain.replace("www.", "")
            name_part = host.split(".")[0]
            spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name_part)
            spaced = spaced.replace("-", " ").replace("_", " ")
            brand = spaced.title()
            if " " not in brand and len(brand) > 8:
                found = _find_spaced_brand(name_part, full_html)
                if found:
                    brand = found
            return brand

        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            parts = re.split(r"\s*[|｜–—·•]\s*", title)
            if len(parts) > 1:
                for p in reversed(parts):
                    p = p.strip()
                    if 2 < len(p) < 40:
                        return p

    except Exception:
        pass
    return filename.rsplit(".", 1)[0][:30]

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
        min_value=10, max_value=80, value=30, step=5,
        help="Only show terms found on at least this % of competitor pages. Lower = more terms shown.",
    )

    custom_sw = st.text_input(
        "Extra stopwords to exclude (comma-separated)",
        placeholder="e.g. brand, cityname, promo",
    )

    top_n = st.slider("Max unigrams to show (bigrams ≈ 60 %, trigrams ≈ 30 %)", 10, 200, 80, step=10)

    st.markdown("---")
    st.subheader("Translation")
    source_lang_label = st.selectbox(
        "Content language",
        options=list(SUPPORTED_LANGUAGES.keys()),
        index=0,
        help="Select the language of the pages you're analysing. This improves translation accuracy — auto-detect can misidentify single words.",
    )
    source_lang = SUPPORTED_LANGUAGES[source_lang_label]

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
        "Green rows = opportunity — competitors use this term more than you.  \n"
        "Red rows = you already mention this term more than competitors."
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
        my_html_bytes = my_file.read()
        my_result = parse_html_bytes(my_html_bytes, url=my_file.name)
        my_result["_raw_html"] = my_html_bytes
        scraped = [my_result]

        for f in comp_files[:10]:
            comp_html_bytes = f.read()
            comp_result = parse_html_bytes(comp_html_bytes, url=f.name)
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
    st.session_state["has_html"] = any(d.get("_raw_html") for d in scraped)

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

    has_html = st.session_state.get("has_html", False)
    tab_names = ["Full Results", "Gap Analysis", "Chart", "Product Listings"]
    tabs = st.tabs(tab_names)
    tab1, tab2, tab3, tab4 = tabs[0], tabs[1], tabs[2], tabs[3]

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

    with tab4:
        st.subheader("Product Listing Analysis")
        st.caption("Detects repeating product patterns in scraped pages and compares how each site structures its product grid.")

        stored_scraped = st.session_state.get("scraped", [])
        pages_with_html = []
        seen_names = {}
        for idx, d in enumerate(stored_scraped):
            raw = d.get("_raw_html")
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if d["url"] == my_url:
                    site_name = "YOUR PAGE"
                else:
                    site_name = _extract_site_name(d["url"], raw)
                if site_name in seen_names:
                    seen_names[site_name] += 1
                    site_name = f"{site_name} ({seen_names[site_name]})"
                else:
                    seen_names[site_name] = 1
                pages_with_html.append({"label": site_name, "html": raw})

        if not pages_with_html:
            st.info("No raw HTML available for product detection. Use 'Scrape from URL' with Firecrawl or upload HTML files.")
        else:
            with st.spinner("Detecting product listings..."):
                pl_results = analyze_multiple_pages(pages_with_html)

            overview_rows = []
            for r in pl_results:
                page_type = r.get("page_type", "unknown")
                if page_type == "blog":
                    status = "📝 Blog / Guide"
                elif page_type == "template":
                    status = "⚠️ Unrendered template"
                elif r["product_count"] > 0:
                    status = f"✅ {r['product_count']} products"
                else:
                    status = "❌ Not detected"
                overview_rows.append({
                    "Page": r["label"],
                    "Page Type": status,
                    "Structure": r.get("structure", ""),
                })

            st.markdown("#### Structure Overview")
            st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

            for r in pl_results:
                with st.expander(f"{r['label']} — {r['product_count']} products in {r['container_tag']}", expanded=False):
                    if not r["products"]:
                        st.warning("No product listings detected on this page.")
                    else:
                        prod_rows = []
                        for p in r["products"]:
                            prod_rows.append({
                                "Product Name": p["name"],
                                "Price": p["price"],
                                "Image Alt Text": p["img_alt"],
                                "URL": p["url"],
                            })
                        st.dataframe(pd.DataFrame(prod_rows), use_container_width=True, hide_index=True)

            all_products = []
            for r in pl_results:
                for p in r["products"]:
                    all_products.append({
                        "Page": r["label"],
                        "Container Tag": r["container_tag"],
                        "Product Name": p["name"],
                        "Price": p["price"],
                        "Image Alt Text": p["img_alt"],
                        "URL": p["url"],
                    })
            if all_products:
                csv_products = pd.DataFrame(all_products).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Product Listings CSV",
                    data=csv_products,
                    file_name="product_listings.csv",
                    mime="text/csv",
                )
