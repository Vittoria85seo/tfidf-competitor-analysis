"""
Keyword Variation Counter — Core Logic

Counting rules:
- Each keyword is matched as a CONTIGUOUS STANDALONE phrase (word boundaries).
- A word embedded inside a longer word does NOT count:
    "veste" does NOT count inside "vestes"
    "snow" does NOT count inside "snowboard"
    "homme" does NOT count inside "hommes"
- Singular and plural are DISTINCT: "manteau" ≠ "manteaux", "peto" ≠ "petos"
- Multi-word keywords must appear together in exact sequence.
- When text contains "veste snowboard homme", each matching keyword from the list
  counts independently (e.g. "veste", "homme", "veste snowboard homme" all get +1).
"""

import re


def count_keyword(text: str, keyword: str) -> int:
    """
    Count occurrences of a keyword as a standalone contiguous phrase.
    Uses word boundaries so "veste" won't match inside "vestes".
    """
    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
    return len(re.findall(pattern, text.lower()))


def strip_html(text: str) -> str:
    """Remove HTML tags, keep text."""
    return re.sub(r'<[^>]+>', ' ', text)


def extract_headings(html: str) -> list:
    """Return list of heading texts from HTML."""
    return [
        strip_html(m.group(1)).strip()
        for m in re.finditer(r'<h[1-6][^>]*>(.*?)</h[1-6]>', html, re.IGNORECASE | re.DOTALL)
    ]


def extract_body(html: str) -> str:
    """Return all paragraph text from HTML."""
    parts = [
        strip_html(m.group(1)).strip()
        for m in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    ]
    return ' '.join(parts) if parts else strip_html(html)


def count_all(text: str, keywords: list) -> dict:
    """
    Count all keywords in text.
    Returns dict: { keyword: count }
    """
    return {kw: count_keyword(text, kw) for kw in keywords}


def count_with_targets(text: str, keyword_list: list) -> list:
    """
    Count keywords and compare against targets.

    keyword_list: list of dicts with keys:
        - keyword (str): the term
        - allowed (int): target count (A value)
        - note (str, optional): user instruction

    Returns list of dicts:
        - keyword, current, allowed, diff, status, note
    """
    results = []
    for item in keyword_list:
        kw = item['keyword']
        a = item.get('allowed', 0)
        note = item.get('note', '')
        c = count_keyword(text, kw)
        diff = a - c
        if diff > 0:
            status = f'need +{diff}'
        elif diff < 0:
            status = f'need {diff}'
        else:
            status = 'OK'
        results.append({
            'keyword': kw,
            'current': c,
            'allowed': a,
            'diff': diff,
            'status': status,
            'note': note
        })
    return results


def parse_ca_line(line: str) -> dict | None:
    """
    Parse a single keyword line in C/A format.

    Accepts:
        veste snowboard homme C:1 A:4
        veste snowboard homme C:1 A:4 add 2
        veste snowboard homme ( 100.00%, C: 1, A: 4 ) remove

    Returns dict with: keyword, current, allowed, note
    """
    line = line.strip()
    if not line:
        return None

    # Format: keyword ( X%, C: N, A: N ) optional_note
    m = re.match(
        r'^(.+?)\s*\(\s*[\d.]+%\s*,\s*C:\s*(\d+)\s*,\s*A:\s*(\d+)\s*\)\s*(.*)?$', line
    )
    if m:
        return {
            'keyword': m.group(1).strip(),
            'current': int(m.group(2)),
            'allowed': int(m.group(3)),
            'note': (m.group(4) or '').strip()
        }

    # Format: keyword C:N A:N optional_note
    m = re.match(r'^(.+?)\s+C:\s*(\d+)\s+A:\s*(\d+)\s*(.*)?$', line)
    if m:
        return {
            'keyword': m.group(1).strip(),
            'current': int(m.group(2)),
            'allowed': int(m.group(3)),
            'note': (m.group(4) or '').strip()
        }

    return None


def parse_ca_list(text: str) -> list:
    """
    Parse a full keyword list in C/A format (one keyword per line).
    Returns list of dicts with: keyword, current, allowed, note
    """
    results = []
    for line in text.strip().splitlines():
        parsed = parse_ca_line(line)
        if parsed:
            results.append(parsed)
    return results
