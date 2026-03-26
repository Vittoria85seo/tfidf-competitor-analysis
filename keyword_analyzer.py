import re
import math
from bs4 import BeautifulSoup


def _normalize(text):
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"['`\u00b4\u2032]", "'", text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()


def count_keyword(text, keyword):
    if not text or not keyword:
        return 0
    text = _normalize(text)
    keyword = _normalize(keyword)
    pattern = r'\b' + re.escape(keyword) + r'\b'
    return len(re.findall(pattern, text))


def extract_elements(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "svg", "path"]):
        tag.decompose()

    wc_soup_title = soup.find("title")
    if wc_soup_title:
        wc_title_text = wc_soup_title.get_text(strip=True)
    else:
        wc_title_text = ""
    wc_full_text = soup.get_text(" ", strip=True)
    if wc_title_text and wc_full_text.startswith(wc_title_text):
        wc_full_text = wc_full_text[len(wc_title_text):].strip()
    pop_word_count = len(wc_full_text.split())

    for tag in soup(["noscript"]):
        tag.decompose()

    meta_title = ""
    title_tag = soup.find("title")
    if title_tag:
        meta_title = title_tag.get_text(strip=True)
    meta_name_title = soup.find("meta", attrs={"name": "title"})
    if meta_name_title:
        mt_content = meta_name_title.get("content", "").strip()
        if mt_content:
            if meta_title:
                meta_title = meta_title + " " + mt_content
            else:
                meta_title = mt_content

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        meta_desc = desc_tag.get("content", "")

    h1_texts = []
    h2_texts = []
    h3_texts = []
    h4_texts = []
    for h in soup.find_all("h1"):
        t = h.get_text(' ', strip=True)
        if t:
            h1_texts.append(t)
    for h in soup.find_all("h2"):
        t = h.get_text(' ', strip=True)
        if t:
            h2_texts.append(t)
    for h in soup.find_all("h3"):
        t = h.get_text(' ', strip=True)
        if t:
            h3_texts.append(t)
    for h in soup.find_all("h4"):
        t = h.get_text(' ', strip=True)
        if t:
            h4_texts.append(t)

    h5_texts = [h.get_text(strip=True) for h in soup.find_all("h5") if h.get_text(strip=True)]
    h6_texts = [h.get_text(strip=True) for h in soup.find_all("h6") if h.get_text(strip=True)]

    p_tags = [p for p in soup.find_all("p") if p.get_text(strip=True)]
    p_text = " ".join(p.get_text(strip=True) for p in p_tags)

    anchor_texts = []
    for a in soup.find_all("a"):
        t = a.get_text(" ", strip=True)
        if t:
            anchor_texts.append(t)
        title = a.get("title", "").strip()
        if title:
            anchor_texts.append(title)
    anchor_text = "\n".join(anchor_texts)

    img_alts = []
    for img in soup.find_all("img", alt=True):
        alt = img.get("alt", "").strip()
        if alt:
            img_alts.append(alt)
    img_alt_text = "\n".join(img_alts)

    bold_texts = []
    for tag in soup.find_all(["b", "strong"]):
        t = tag.get_text(" ", strip=True)
        if t:
            bold_texts.append(t)
    bold_text = "\n".join(bold_texts)

    italic_texts = []
    for tag in soup.find_all(["i", "em"]):
        t = tag.get_text(" ", strip=True)
        if t:
            italic_texts.append(t)
    italic_text = "\n".join(italic_texts)

    body_parts = []
    for tag in soup.find_all(["p", "li", "span"]):
        t = tag.get_text(strip=True)
        if t:
            body_parts.append(t)
    body_text = " ".join(body_parts)

    title_tag_ft = soup.find("title")
    if title_tag_ft:
        title_tag_ft.decompose()
    full_text = soup.get_text(" ", strip=True)

    return {
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "h1": " ".join(h1_texts),
        "h2": " ".join(h2_texts),
        "h3": " ".join(h3_texts),
        "h4": " ".join(h4_texts),
        "p_text": p_text,
        "anchor_text": anchor_text,
        "img_alt": img_alt_text,
        "bold": bold_text,
        "italic": italic_text,
        "body": body_text,
        "full_text": full_text,
        "h1_count": len(h1_texts),
        "h2_count": len(h2_texts),
        "h3_count": len(h3_texts),
        "h4_count": len(h4_texts),
        "h5_count": len(h5_texts),
        "h6_count": len(h6_texts),
        "p_count": len(p_tags),
        "section_count": len(h2_texts) + len(h3_texts) + len(h4_texts),
        "word_count": len(body_text.split()),
        "full_text_word_count": pop_word_count,
    }


ELEMENTS = ["meta_title", "meta_description", "h1", "h2", "h3", "h4", "body"]
ELEMENTS_NO_META_DESC = ["meta_title", "h1", "h2", "h3", "h4", "body"]
ELEMENT_LABELS = {
    "meta_title": "Meta Title",
    "meta_description": "Meta Description",
    "h1": "H1",
    "h2": "H2",
    "h3": "H3",
    "h4": "H4",
    "body": "Body (P + LI)",
}


def count_keyword_per_element(elements, keyword):
    return {el: count_keyword(elements[el], keyword) for el in ELEMENTS}


def rank_weights(n):
    if n <= 0:
        return []
    weights = []
    for i in range(n):
        weights.append(1.0 / (i + 1))
    total = sum(weights)
    return [w / total for w in weights]


def detect_outliers(values, threshold=2.0):
    if len(values) < 3:
        return [False] * len(values)
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return [False] * len(values)
    return [abs(v - mean) > threshold * std for v in values]


def weighted_average(values, weights, exclude_outliers=True):
    if not values:
        return 0.0
    if exclude_outliers and len(values) >= 3:
        outliers = detect_outliers(values)
        filtered = [(v, w) for v, w, o in zip(values, weights, outliers) if not o]
        if filtered:
            values = [f[0] for f in filtered]
            weights = [f[1] for f in filtered]
            total_w = sum(weights)
            weights = [w / total_w for w in weights]

    return sum(v * w for v, w in zip(values, weights))


def compute_range(values, exclude_outliers=True):
    if not values:
        return 0, 0
    if exclude_outliers and len(values) >= 3:
        outliers = detect_outliers(values)
        filtered = [v for v, o in zip(values, outliers) if not o]
        if filtered:
            values = filtered
    return min(values), max(values)


def analyze_exact_match(target_elements, competitor_elements_list, keyword):
    competitor_elements_list, _ = filter_low_wordcount_competitors(target_elements, competitor_elements_list)
    target_counts = count_keyword_per_element(target_elements, keyword)

    comp_counts_per_element = {el: [] for el in ELEMENTS}
    for comp_el in competitor_elements_list:
        counts = count_keyword_per_element(comp_el, keyword)
        for el in ELEMENTS:
            comp_counts_per_element[el].append(counts[el])

    n_comps = len(competitor_elements_list)
    weights = rank_weights(n_comps)

    results = []
    for el in ELEMENTS:
        c_val = target_counts[el]
        comp_vals = comp_counts_per_element[el]
        avg = weighted_average(comp_vals, weights)
        low, high = compute_range(comp_vals)
        n_have = sum(1 for v in comp_vals if v > 0)
        pct_have = n_have / len(comp_vals) if comp_vals else 0
        if avg >= 1:
            target = round(avg)
        elif pct_have >= 0.2:
            target = 1
        else:
            target = 0
        diff = target - c_val
        if diff > 0:
            status = f"Need +{diff}"
        elif diff < 0:
            status = f"Over by {abs(diff)}"
        else:
            status = "OK"
        results.append({
            "Element": ELEMENT_LABELS[el],
            "Your Page": c_val,
            "Target": target,
            "Comp. Range": f"{low}–{high}",
            "Status": status,
        })

    return results


def analyze_variations(target_elements, competitor_elements_list, variations, secondary_keywords=None):
    competitor_elements_list, _ = filter_low_wordcount_competitors(target_elements, competitor_elements_list)
    n_comps = len(competitor_elements_list)
    if secondary_keywords is None:
        secondary_keywords = []
    secondary_set = {_normalize(sk) for sk in secondary_keywords if sk.strip()}

    results = []
    for kw in variations:
        kw = kw.strip()
        if not kw:
            continue

        total_c = count_keyword(target_elements.get("full_text", ""), kw)

        comp_totals = []
        for comp_el in competitor_elements_list:
            comp_totals.append(count_keyword(comp_el.get("full_text", ""), kw))

        total_avg = round(sum(comp_totals) / len(comp_totals)) if comp_totals else 0

        if _normalize(kw) in secondary_set:
            importance = 100.0
        else:
            has_count = sum(1 for c in comp_totals if c > 0)
            raw_pct = (has_count / n_comps) * 100 if n_comps > 0 else 0
            importance = max(10.0, min(90.0, round(raw_pct, 2)))

        results.append({
            "Keyword": kw,
            "C": total_c,
            "A": total_avg,
            "Importance": importance,
        })

    results.sort(key=lambda r: (-r["Importance"], r["Keyword"]))
    return results


VARIATION_ELEMENTS = [
    ("Meta Title", "meta_title"),
    ("Meta Description", "meta_description"),
    ("H1", "h1"),
    ("H2", "h2"),
    ("H3", "h3"),
    ("H4", "h4"),
    ("Paragraph Text", "body"),
    ("Anchor Text", "anchor_text"),
    ("Image alt", "img_alt"),
    ("Bold", "bold"),
    ("Italic", "italic"),
]


_ELEMENT_CONFIG = {
    "meta_title":       {"scale": True,  "rounds": 0, "formula": "avg+std"},
    "meta_description": {"scale": False, "rounds": 0, "formula": "avg+std"},
    "h1":               {"scale": True,  "rounds": 0, "formula": "med+max"},
    "h2":               {"scale": False, "rounds": 3, "formula": "avg+std"},
    "h3":               {"scale": True,  "rounds": 1, "formula": "med+max"},
    "h4":               {"scale": True,  "rounds": 1, "formula": "med+max"},
    "body":             {"scale": True,  "rounds": 3, "formula": "avg+std"},
    "anchor_text":      {"scale": True,  "rounds": 1, "formula": "avg+std"},
    "img_alt":          {"scale": False, "rounds": 3, "formula": "med+max"},
    "bold":             {"scale": False, "rounds": 2, "formula": "med+max"},
    "italic":           {"scale": True,  "rounds": 1, "formula": "avg+std"},
}

def _variation_range(raw_counts, target_wc=0, comp_wcs=None, el_key=""):
    import statistics as _stats
    cfg = _ELEMENT_CONFIG.get(el_key, {"scale": True, "rounds": 3, "formula": "avg+std"})
    if cfg["scale"] and target_wc > 0 and comp_wcs and len(comp_wcs) == len(raw_counts):
        scaled = [raw_counts[i] * (target_wc / comp_wcs[i]) if comp_wcs[i] > 0 else 0.0
                  for i in range(len(raw_counts))]
    else:
        scaled = [float(v) for v in raw_counts]
    rounds = cfg["rounds"]
    filtered = _remove_outliers(scaled, rounds=rounds) if rounds > 0 else scaled[:]
    if not filtered:
        filtered = scaled
    if cfg["formula"] == "med+max":
        med = _stats.median(filtered)
        mx = max(filtered)
        return max(0, round(med)), round(mx)
    avg = sum(filtered) / len(filtered)
    sample_std = (sum((v - avg) ** 2 for v in filtered) / (len(filtered) - 1)) ** 0.5 if len(filtered) > 1 else 0
    return max(0, round(avg)), round(avg + sample_std)


def filter_low_wordcount_competitors(target_elements, competitor_elements_list):
    comp_wcs = [cel.get("full_text_word_count", 0) for cel in competitor_elements_list]
    if len(comp_wcs) < 3:
        return competitor_elements_list, comp_wcs
    values = [float(v) for v in comp_wcs]
    avg = sum(values) / len(values)
    pop_std = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
    if pop_std == 0:
        return competitor_elements_list, comp_wcs
    threshold = avg - 1.0 * pop_std
    kept = [(cel, wc) for cel, wc in zip(competitor_elements_list, comp_wcs) if wc >= threshold]
    if len(kept) < 3:
        return competitor_elements_list, comp_wcs
    return [k[0] for k in kept], [k[1] for k in kept]


_STRUCTURAL_ELEMENTS = {"h3", "anchor_text", "img_alt", "italic", "meta_description"}

def analyze_variation_elements(target_elements, competitor_elements_list, variations):
    all_competitor_elements = competitor_elements_list[:]
    filtered_competitors, _ = filter_low_wordcount_competitors(target_elements, competitor_elements_list)
    n_comps = len(filtered_competitors)
    if not variations or n_comps == 0:
        return []

    clean_variations = [kw.strip() for kw in variations if kw.strip()]

    target_wc = target_elements.get("full_text_word_count", 0)
    filtered_wcs = [cel.get("full_text_word_count", 0) for cel in filtered_competitors]
    all_wcs = [cel.get("full_text_word_count", 0) for cel in all_competitor_elements]

    comp_raw = {}
    comp_raw_all = {}
    for label, el_key in VARIATION_ELEMENTS:
        raw_counts = []
        for comp_el in filtered_competitors:
            total = sum(count_keyword(comp_el.get(el_key, ""), kw) for kw in clean_variations)
            raw_counts.append(total)
        comp_raw[el_key] = raw_counts

        if el_key in _STRUCTURAL_ELEMENTS:
            raw_all = []
            for comp_el in all_competitor_elements:
                total = sum(count_keyword(comp_el.get(el_key, ""), kw) for kw in clean_variations)
                raw_all.append(total)
            comp_raw_all[el_key] = raw_all

    results = []
    for label, el_key in VARIATION_ELEMENTS:
        current = sum(count_keyword(target_elements.get(el_key, ""), kw) for kw in clean_variations)
        if el_key in _STRUCTURAL_ELEMENTS:
            raw_counts = comp_raw_all[el_key]
            target_min, target_max = _variation_range(raw_counts, target_wc, all_wcs, el_key=el_key)
        else:
            raw_counts = comp_raw[el_key]
            target_min, target_max = _variation_range(raw_counts, target_wc, filtered_wcs, el_key=el_key)

        if current < target_min:
            diff = target_min - current
            rec = f"Increase the number of variations of your keyword in your {label} by {diff}"
            severity = "HIGH" if diff > target_max * 0.5 and target_max > 0 else "MID"
        elif current > target_max and target_max > 0:
            diff = current - target_max
            rec = f"Reduce the number of variations of your keyword in your {label} by {diff}"
            severity = "HIGH" if diff > target_max else "MID"
        else:
            rec = "Leave As Is"
            severity = "GOOD"

        results.append({
            "Where": label,
            "Current": current,
            "Target min": target_min,
            "Target max": target_max,
            "Recommendation": rec,
            "Severity": severity,
        })

    h2_raw_all = comp_raw_all.get("h2", None)
    if h2_raw_all is None:
        h2_raw_all = [sum(count_keyword(c.get("h2", ""), kw) for kw in clean_variations) for c in all_competitor_elements]
    h3_raw_all = comp_raw_all.get("h3", comp_raw.get("h3", []))
    if len(h2_raw_all) != len(h3_raw_all):
        h3_raw_all = [sum(count_keyword(c.get("h3", ""), kw) for kw in clean_variations) for c in all_competitor_elements]
    h2h3_raw = [a + b for a, b in zip(h2_raw_all, h3_raw_all)]
    h2h3_current = (
        sum(count_keyword(target_elements.get("h2", ""), kw) for kw in clean_variations) +
        sum(count_keyword(target_elements.get("h3", ""), kw) for kw in clean_variations)
    )
    h2h3_min, h2h3_max = _variation_range(h2h3_raw, target_wc, all_wcs, el_key="h2")

    if h2h3_current < h2h3_min:
        diff = h2h3_min - h2h3_current
        h2h3_rec = (
            f"Although your individual signals might be correct, its possible that you are under optimized in total. "
            f"Consider increasing variations of your keyword in H2s or H3s by {diff}"
        )
        h2h3_sev = "MID"
    elif h2h3_current > h2h3_max and h2h3_max > 0:
        diff = h2h3_current - h2h3_max
        h2h3_rec = f"Consider reducing variations of your keyword in H2s or H3s by {diff}"
        h2h3_sev = "MID"
    else:
        h2h3_rec = "Leave As Is"
        h2h3_sev = "GOOD"

    results.append({
        "Where": "H2 to H3",
        "Current": h2h3_current,
        "Target min": h2h3_min,
        "Target max": h2h3_max,
        "Recommendation": h2h3_rec,
        "Severity": h2h3_sev,
    })

    return results


def _remove_outliers(values, rounds=3):
    if len(values) <= 3:
        return values[:]
    import statistics
    for _ in range(rounds):
        if len(values) <= 3:
            break
        mean = statistics.mean(values)
        std = statistics.pstdev(values)
        if std == 0:
            break
        filtered = [v for v in values if abs(v - mean) <= 1.5 * std]
        if not filtered or len(filtered) == len(values):
            break
        values = filtered
    return values


def analyze_sections(target_elements, competitor_elements_list):
    competitor_elements_list, _ = filter_low_wordcount_competitors(target_elements, competitor_elements_list)
    metrics = [
        ("H1 Tag Total", "h1_count"),
        ("H2 Tag Total", "h2_count"),
        ("H3 Tag Total", "h3_count"),
        ("H4 Tag Total", "h4_count"),
        ("H5 Tag Total", "h5_count"),
        ("H6 Tag Total", "h6_count"),
        ("Paragraph Text Tag Total", "p_count"),
        ("Word Count (Body)", "word_count"),
    ]

    results = []
    for label, key in metrics:
        c_val = target_elements.get(key, 0)
        comp_vals = [comp.get(key, 0) for comp in competitor_elements_list]
        filtered = _remove_outliers(comp_vals)
        low = min(filtered) if filtered else 0
        high = max(filtered) if filtered else 0
        avg = sum(filtered) / len(filtered) if filtered else 0

        diff = avg - c_val
        if "Word Count" in label:
            if diff > 50:
                rec = f"Increase the total number on your page by {int(diff)}"
            elif diff < -50:
                rec = f"Reduce the total number on your page by {abs(int(diff))}"
            else:
                rec = "Leave As Is"
        else:
            if diff > 0.5:
                rec = f"Increase the total number on your page by {math.ceil(diff)}"
            elif diff < -0.5:
                rec = f"Reduce the total number on your page by {abs(math.floor(diff))}"
            else:
                rec = "Leave As Is"
        results.append({
            "Where": label,
            "Lowest": low,
            "Highest": high,
            "Average": round(avg, 2),
            "Current": c_val,
            "Recommendation": rec,
        })

    return results
