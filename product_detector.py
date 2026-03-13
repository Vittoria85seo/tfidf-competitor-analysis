import re
from collections import Counter
from bs4 import BeautifulSoup


def _clean_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_price(text):
    return bool(re.search(r"\d+[.,]?\d*\s*(kr|:-|sek|eur|€|\$|£|usd|nok|dkk|pln|czk)", text, re.IGNORECASE))


def _has_template_syntax(html_content):
    snippet = html_content[:50000]
    liquid_patterns = [r"\{\{.*?\}\}", r"\{%.*?%\}"]
    matches = 0
    for pat in liquid_patterns:
        matches += len(re.findall(pat, snippet))
    return matches > 20


def _is_nav_element(element):
    nav_class_patterns = re.compile(
        r"(?<![a-z-])(nav|menu|footer|header|sidebar|breadcrumb|cookie|banner|toolbar|dropdown)(?![a-z-])",
        re.IGNORECASE
    )
    nav_keywords = ["menu", "footer", "header", "sidebar", "breadcrumb",
                     "cookie", "banner", "toolbar", "topbar", "dropdown"]
    skip_ids = {"chakra-skip-nav", "skip-nav", "skipnav", "skip-to-content"}
    for ancestor in element.parents:
        if ancestor.name in ("nav", "header", "footer"):
            if ancestor.name == "nav":
                return True
            if ancestor.name in ("header", "footer"):
                role = (ancestor.get("role") or "").lower()
                if role in ("banner", "contentinfo", "navigation"):
                    return True
                ancestor_classes = " ".join(ancestor.get("class", [])).lower()
                if "site" in ancestor_classes or "global" in ancestor_classes or "main" in ancestor_classes:
                    return True
        ancestor_classes = " ".join(ancestor.get("class", [])).lower()
        ancestor_id = (ancestor.get("id") or "").lower()
        if ancestor_id in skip_ids:
            continue
        if nav_class_patterns.search(ancestor_classes):
            return True
        if ancestor_id and any(kw in ancestor_id for kw in nav_keywords):
            return True
    return False


def _is_blog_page(soup):
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")
           if len(h.get_text(strip=True)) > 5 and not _is_nav_element(h)]
    if 3 <= len(h2s) <= 10:
        content_words = set()
        for h in h2s:
            content_words.update(h.lower().split())
        guide_words = {"comment", "choisir", "guide", "how", "choose", "types",
                       "différent", "different", "tips", "conseil", "why", "what",
                       "caractéristiques", "features", "vs", "comparaison",
                       "hardshell", "softshell", "imperméabilité", "respirabilité",
                       "coupes", "ajustement"}
        guide_matches = len(content_words & guide_words)
        if guide_matches >= 3:
            article_tags = soup.find_all("article")
            if len(article_tags) == 1:
                return True
            main_content = soup.find("main") or soup
            h3s = main_content.find_all("h3")
            non_nav_h3s = [h for h in h3s if not _is_nav_element(h)]
            if len(non_nav_h3s) >= 5:
                return True
    return False


def _get_name_from_element(el):
    for tag in ("h2", "h3", "h4"):
        heading = el.find(tag)
        if heading:
            txt = _clean_text(heading.get_text(strip=True))
            if 5 <= len(txt) <= 200:
                tag_cls = " ".join(heading.get("class", []))
                return txt, f"<{tag}>", tag_cls

    product_name_selectors = [
        ("p", re.compile(r"product.*name|name.*title|item.*name", re.IGNORECASE)),
        ("span", re.compile(r"product.*name|name.*title|item.*name", re.IGNORECASE)),
        ("div", re.compile(r"product.*name|name.*title|item.*name|meta.*title", re.IGNORECASE)),
        ("a", re.compile(r"product.*name|name.*title|item.*name", re.IGNORECASE)),
    ]
    for tag, pattern in product_name_selectors:
        for child in el.find_all(tag, class_=True):
            cls = " ".join(child.get("class", []))
            if pattern.search(cls):
                txt = _clean_text(child.get_text(strip=True))
                if 5 <= len(txt) <= 200:
                    return txt, f"<{tag}>", cls

    img = el.find("img", alt=True)
    if img:
        alt = img["alt"].strip()
        alt = re.sub(r"\s*-\s*product\s*image\s*$", "", alt, flags=re.IGNORECASE)
        if len(alt) > 10:
            return alt, "<img alt>", ""

    return None, None, None


def _extract_product_from_card(el):
    name, name_tag, name_class = _get_name_from_element(el)
    if not name:
        return None, None, None

    price = ""
    text = el.get_text(strip=True)
    price_match = re.search(
        r"(\d+[.,]?\d*\s*(?:kr|:-|sek|eur|€|\$|£|usd|nok|dkk|pln|czk))",
        text, re.IGNORECASE
    )
    if price_match:
        price = price_match.group(1)

    img_alt = ""
    img = el.find("img", alt=True)
    if img and len(img["alt"].strip()) > 3:
        img_alt = img["alt"].strip()

    product_url = ""
    link = el.find("a", href=True)
    if link:
        href = link.get("href", "")
        if href and href != "#" and not href.startswith("javascript"):
            product_url = href

    product = {
        "name": name[:150],
        "price": price,
        "img_alt": img_alt[:150],
        "url": product_url[:200],
    }
    return product, name_tag, name_class


def _score_candidate(tag_name, class_str, elements, products, avg_name_len):
    score = 0
    score += min(len(elements), 50)
    sample = elements[:10]
    has_img = sum(1 for el in sample if el.find("img"))
    has_link = sum(1 for el in sample if el.find("a", href=True))
    score += has_img * 3
    score += has_link * 2
    if tag_name in ("li", "article"):
        score += 10
    elif tag_name == "div":
        score += 5
    class_lower = class_str.lower()
    product_keywords = ["product", "item", "card", "tile", "listing"]
    if any(kw in class_lower for kw in product_keywords):
        score += 20
    nav_keywords_list = ["menu", "nav", "footer", "header", "sidebar",
                         "breadcrumb", "cookie", "mega-menu"]
    if any(kw in class_lower for kw in nav_keywords_list):
        score -= 50
    if avg_name_len > 20:
        score += 10
    return score


def _extract_group_candidate(elements, tag_name, class_str, parent_name):
    products = []
    name_tags = Counter()
    name_classes = Counter()
    for el in elements:
        product, ntag, ncls = _extract_product_from_card(el)
        if product:
            products.append(product)
            if ntag:
                name_tags[ntag] += 1
            if ncls:
                name_classes[ncls] += 1

    if len(products) < 3:
        return None

    avg_name_len = sum(len(p["name"]) for p in products) / len(products)
    if avg_name_len < 8:
        return None

    best_name_tag = name_tags.most_common(1)[0][0] if name_tags else ""
    best_name_class = name_classes.most_common(1)[0][0] if name_classes else ""
    score = _score_candidate(tag_name, class_str, elements, products, avg_name_len)
    if best_name_tag and best_name_tag != "<img alt>":
        score += 5

    data_attrs = {}
    sample_el = elements[0]
    for k, v in sample_el.attrs.items():
        if k.startswith("data-") and k not in ("data-page-optimizer-init",
                                                 "data-is-editor-editing"):
            data_attrs[k] = v
            if len(data_attrs) >= 2:
                break

    return {
        "container_tag": f"<{tag_name}>",
        "container_class": class_str,
        "container_data": data_attrs,
        "parent_tag": f"<{parent_name}>",
        "name_tag": best_name_tag,
        "name_class": best_name_class,
        "product_count": len(products),
        "products": products,
        "score": score,
    }


def _find_product_groups(soup):
    candidates = []

    for parent in soup.find_all(True):
        if _is_nav_element(parent):
            continue
        children = [c for c in parent.children if hasattr(c, "name") and c.name]
        if len(children) < 4:
            continue

        tag_class_counts = Counter()
        tag_class_elements = {}
        for child in children:
            classes = tuple(sorted(child.get("class", [])))
            key = (child.name, classes)
            tag_class_counts[key] += 1
            if key not in tag_class_elements:
                tag_class_elements[key] = []
            tag_class_elements[key].append(child)

        for key, count in tag_class_counts.items():
            if count < 4:
                continue
            elements = tag_class_elements[key]
            tag_name = key[0]
            class_str = " ".join(key[1]) if key[1] else "(no class)"
            candidate = _extract_group_candidate(
                elements, tag_name, class_str, parent.name)
            if candidate:
                candidates.append(candidate)

    product_class_pattern = re.compile(
        r"product|prod-card|card(?!-header|ousel)|tile|listing", re.IGNORECASE)
    global_class_groups = Counter()
    global_class_elements = {}
    for el in soup.find_all(["li", "article", "div", "section"]):
        classes = tuple(sorted(el.get("class", [])))
        if not classes:
            continue
        cls_str = " ".join(classes)
        if not product_class_pattern.search(cls_str):
            continue
        key = (el.name, classes)
        global_class_groups[key] += 1
        if key not in global_class_elements:
            global_class_elements[key] = []
        global_class_elements[key].append(el)

    for key, count in global_class_groups.items():
        if count < 4:
            continue
        elements = global_class_elements[key]
        non_nav = [el for el in elements if not _is_nav_element(el)]
        if len(non_nav) < 4:
            continue
        tag_name = key[0]
        class_str = " ".join(key[1])
        already_found = any(
            c["container_tag"] == f"<{tag_name}>"
            and c["container_class"] == class_str
            for c in candidates
        )
        if already_found:
            continue
        candidate = _extract_group_candidate(
            non_nav, tag_name, class_str, "global")
        if candidate:
            candidate["score"] += 5
            candidates.append(candidate)

    testid_pattern = re.compile(r"product", re.IGNORECASE)
    testid_groups = Counter()
    testid_elements = {}
    for el in soup.find_all(["li", "article", "div", "section", "a"]):
        testid = el.get("data-testid", "")
        if not testid or not testid_pattern.search(testid):
            continue
        if "price" in testid.lower() or "rating" in testid.lower():
            continue
        key = (el.name, testid)
        testid_groups[key] += 1
        if key not in testid_elements:
            testid_elements[key] = []
        testid_elements[key].append(el)

    for key, count in testid_groups.items():
        if count < 4:
            continue
        elements = testid_elements[key]
        non_nav = [el for el in elements if not _is_nav_element(el)]
        if len(non_nav) < 4:
            continue
        tag_name = key[0]
        testid_str = key[1]
        candidate = _extract_group_candidate(
            non_nav, tag_name, testid_str, "testid")
        if candidate:
            candidate["score"] += 10
            candidates.append(candidate)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates



def _find_structure_path(soup, products, container_tag, name_tag_str):
    ct = container_tag.strip("<>")
    nt = name_tag_str.strip("<>")
    if not products or not nt:
        return f"{ct}+{nt}" if ct and nt else ct or nt or ""

    sample_name = products[0].get("name", "")
    if not sample_name or len(sample_name) < 5:
        return f"{ct}+{nt}" if ct and nt else ct or nt or ""

    name_el = None
    if nt == "img alt":
        for img in soup.find_all("img", alt=True):
            if img["alt"].strip()[:30] == sample_name[:30]:
                name_el = img
                break
    else:
        bare_tag = nt
        for el in soup.find_all(bare_tag):
            if el.get_text(strip=True)[:30] == sample_name[:30]:
                name_el = el
                break

    if not name_el:
        return f"{ct}+{nt}" if ct and nt else ct or nt or ""

    structural = {"li", "article", "section", "div"}
    stop_tags = {"ul", "ol", "body", "main", "html", "nav", "header", "footer"}
    path_tags = []
    el = name_el.parent if nt != "img alt" else name_el.parent
    depth = 0
    while el and el.name and depth < 20:
        if el.name in stop_tags:
            break
        if el.name in structural:
            path_tags.append(el.name)
        el = el.parent
        depth += 1

    if path_tags:
        outer = path_tags[-1]
        return f"{outer}+{nt}"
    return f"{ct}+{nt}" if ct and nt else ct or nt or ""


def detect_product_listings(html_content):
    if isinstance(html_content, bytes):
        html_content = html_content.decode("utf-8", errors="replace")

    if _has_template_syntax(html_content):
        return {"is_template": True}

    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["script", "noscript"]):
        tag.decompose()
    for tag in soup(["style"]):
        tag.string = ""

    if _is_blog_page(soup):
        return {"is_blog": True}

    candidates = _find_product_groups(soup)

    if candidates:
        best = candidates[0]
        products = best["products"]
        name_tag = best["name_tag"]
        if products and name_tag == "<img alt>":
            names = [p["name"] for p in products]
            unique_names = set(names)
            if len(unique_names) <= 2:
                raw_products = _extract_products_from_raw_html(html_content)
                if raw_products and len(raw_products) >= len(products) * 0.5:
                    products = raw_products[:len(products)]
                    name_tag = "<span>"
                    best["products"] = products
                    best["name_tag"] = name_tag
        data_str = ""
        if best.get("container_data"):
            data_str = " ".join(f'{k}="{v}"' for k, v in list(best["container_data"].items())[:2])
        structure = _find_structure_path(
            soup, best["products"], best["container_tag"], best["name_tag"])
        return {
            "container_tag": best["container_tag"],
            "container_class": best["container_class"],
            "container_data": data_str,
            "parent_tag": best["parent_tag"],
            "name_tag": best["name_tag"],
            "name_class": best["name_class"],
            "structure": structure,
            "product_count": best["product_count"],
            "products": best["products"],
            "score": best["score"],
        }

    return None


def _extract_products_from_raw_html(html_content):
    price_pattern = re.compile(
        r"(\d+[.,]?\d*)\s*(?::-|kr|:-|sek|€|\$|£)", re.IGNORECASE)
    price_testid = re.compile(
        r'>([^<]{10,120})</span></section><section[^>]*data-testid=["\']?(?:new-)?product-card-price',
        re.IGNORECASE)
    anchored = price_testid.findall(html_content)
    if len(anchored) >= 4:
        products = []
        price_matches = re.finditer(
            r'data-testid=["\']?current-price["\']?[^>]*>([^<]+)<', html_content)
        prices = [m.group(1).strip() for m in price_matches]
        for i, name in enumerate(anchored):
            name = name.strip()
            price = prices[i] if i < len(prices) else ""
            products.append({"name": name[:150], "price": price, "img_alt": "", "url": ""})
        return products
    card_splits = re.split(
        r'data-testid=["\']?(?:new-)?product-card', html_content, flags=re.IGNORECASE)
    if len(card_splits) < 5:
        return []
    products = []
    for chunk in card_splits[1:]:
        chunk = chunk[:3000]
        name = ""
        spans = re.findall(r">([^<]{10,80})<\/span>", chunk)
        for sp in spans:
            sp = sp.strip()
            if (not price_pattern.search(sp)
                    and not sp.startswith("http")
                    and any(c.isalpha() for c in sp)
                    and "star" not in sp.lower()
                    and "rating" not in sp.lower()
                    and "pris" not in sp.lower()
                    and "price" not in sp.lower()):
                name = sp
                break
        if name:
            price = ""
            pm = price_pattern.search(chunk)
            if pm:
                price = pm.group(0)
            products.append({"name": name[:150], "price": price, "img_alt": "", "url": ""})
    return products


def analyze_multiple_pages(pages_data):
    results = []
    for page in pages_data:
        label = page["label"]
        html = page["html"]

        listing = detect_product_listings(html)
        if listing and listing.get("is_blog"):
            results.append({
                "label": label,
                "container_tag": "Blog / Guide page",
                "container_class": "",
                "parent_tag": "",
                "name_tag": "",
                "name_class": "",
                "product_count": 0,
                "products": [],
                "page_type": "blog",
            })
        elif listing and listing.get("is_template"):
            results.append({
                "label": label,
                "container_tag": "Unrendered template",
                "container_class": "",
                "parent_tag": "",
                "name_tag": "",
                "name_class": "",
                "product_count": 0,
                "products": [],
                "page_type": "template",
            })
        elif listing:
            results.append({
                "label": label,
                "container_tag": listing["container_tag"],
                "container_class": listing["container_class"],
                "parent_tag": listing.get("parent_tag", ""),
                "name_tag": listing.get("name_tag", ""),
                "name_class": listing.get("name_class", ""),
                "structure": listing.get("structure", ""),
                "product_count": listing["product_count"],
                "products": listing["products"],
                "page_type": "product_listing",
            })
        else:
            results.append({
                "label": label,
                "container_tag": "Not detected",
                "container_class": "",
                "parent_tag": "",
                "name_tag": "",
                "name_class": "",
                "product_count": 0,
                "products": [],
                "page_type": "unknown",
            })

    return results
