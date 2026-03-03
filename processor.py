import re
import pandas as pd
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer

nltk.download("stopwords", quiet=True)
from nltk.corpus import stopwords as nltk_stopwords

UI_WORDS = {
    "login", "logout", "account", "register", "sign", "signup", "signin",
    "cart", "menu", "home", "search", "cookie", "cookies", "privacy", "terms",
    "contact", "newsletter", "subscribe", "unsubscribe", "checkout",
    "password", "username", "submit", "copyright", "sitemap", "faq", "help",
    "facebook", "twitter", "instagram", "linkedin", "youtube", "pinterest",
    "share", "follow", "like", "comment", "breadcrumb", "navigation",
    "footer", "header", "sidebar", "widget", "popup", "modal",
    "html", "css", "javascript", "script", "iframe", "div", "span", "class",
    "href", "src", "alt", "rel", "http", "https", "www", "url",
    "storage", "session", "local", "persistent", "duration", "maximum",
    "pending", "type", "localstorage", "sessionstorage",
    "consent", "gdpr", "necessary", "functional", "analytics", "performance",
    "pixel", "tracker", "tracking", "beacon",
    "utm", "campaign", "source", "medium",
}

ECOMMERCE_JUNK = {
    "pris", "price", "rea", "sale", "rabatt", "discount", "spara", "save",
    "inklusive", "moms", "vat", "tax", "sku", "stock", "lager",
    "checkout", "varukorg", "kundvagn", "basket", "wishlist", "önskelista",
    "leverans", "frakt", "shipping", "delivery", "retur", "return",
    "beställning", "order",
}

CURRENCIES = {
    "sek", "eur", "usd", "gbp", "nok", "dkk", "pln", "chf", "czk",
    "kr", "euro", "dollar", "pound",
}

CLOTHING_SIZES = {
    "xxs", "xs", "sm", "md", "lg", "xl", "xxl", "xxxl", "xxxxl",
    "xss", "xls",
}

PREPOSITIONS = {
    "about", "above", "across", "after", "against", "along", "among",
    "around", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "during", "except", "inside", "into", "near", "off", "onto",
    "outside", "over", "past", "since", "through", "throughout", "till",
    "toward", "under", "until", "upon", "within", "without",
}

NLTK_LANGS = [
    "english", "italian", "french", "german", "spanish", "portuguese",
    "dutch", "finnish", "swedish", "norwegian", "danish", "hungarian",
    "romanian", "russian", "turkish",
]


def _build_stopwords(custom_words=None):
    sw = set()
    for lang in NLTK_LANGS:
        try:
            sw.update(nltk_stopwords.words(lang))
        except Exception:
            pass
    sw.update(UI_WORDS)
    sw.update(ECOMMERCE_JUNK)
    sw.update(CURRENCIES)
    sw.update(CLOTHING_SIZES)
    sw.update(PREPOSITIONS)
    if custom_words:
        sw.update(w.strip().lower() for w in custom_words if w.strip())
    return sw


def _clean(text):
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_tfidf(scraped_data, my_url, presence_threshold=0.3, custom_stopwords=None):
    sw = _build_stopwords(custom_stopwords)

    my_doc = next(
        (d for d in scraped_data if d["url"] == my_url and not d.get("error")), None
    )
    if not my_doc:
        raise ValueError(f"Could not scrape your URL: {my_url}")

    comp_docs = [
        d for d in scraped_data if d["url"] != my_url and not d.get("error")
    ]
    if not comp_docs:
        raise ValueError("No competitor URLs were successfully scraped.")

    n_comp = len(comp_docs)
    all_docs = [my_doc] + comp_docs
    texts = [_clean(d["combined"]) for d in all_docs]

    rows = []
    for ngram_range, label in [((1, 1), "Unigram"), ((2, 2), "Bigram"), ((3, 3), "Trigram")]:
        try:
            vec = TfidfVectorizer(
                ngram_range=ngram_range,
                min_df=1,
                max_features=10000,
                sublinear_tf=True,
            )
            tfidf_matrix = vec.fit_transform(texts).toarray()

            count_vec = CountVectorizer(
                ngram_range=ngram_range,
                vocabulary=vec.vocabulary_,
            )
            count_matrix = count_vec.transform(texts).toarray()
        except ValueError:
            continue

        terms = vec.get_feature_names_out()
        comp_tfidf = tfidf_matrix[1:]
        my_counts = count_matrix[0]
        comp_counts = count_matrix[1:]

        for i, term in enumerate(terms):
            tokens = term.split()

            if any(t in sw for t in tokens):
                continue

            if not all(re.match(r'^[^\W\d_]+$', t, re.UNICODE) for t in tokens):
                continue

            if label == "Unigram":
                if len(tokens[0]) < 3:
                    continue
            else:
                if any(len(t) < 2 for t in tokens):
                    continue

            comp_present = (comp_tfidf[:, i] > 0).sum()
            comp_presence_frac = comp_present / n_comp
            if comp_presence_frac < presence_threshold:
                continue

            my_mention = int(my_counts[i])
            avg_comp_mentions = round(float(comp_counts[:, i].mean()), 1)
            found = my_mention > 0

            rows.append({
                "Keyword / Phrase": term,
                "N-gram Type": label,
                "Mentions (My Page)": my_mention,
                "Avg Mentions (Competitors)": avg_comp_mentions,
                "% Competitors Using": round(comp_presence_frac * 100, 1),
                "Found In My Page": "Yes" if found else "No",
                "_opportunity": avg_comp_mentions > my_mention and avg_comp_mentions >= 1,
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("Avg Mentions (Competitors)", ascending=False).reset_index(drop=True)
    return df
