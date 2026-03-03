import time
from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator


def detect_language(text):
    try:
        return detect(text[:2000])
    except LangDetectException:
        return "en"


def has_non_english(scraped_data):
    for doc in scraped_data:
        if not doc.get("error") and doc.get("combined"):
            lang = detect_language(doc["combined"])
            if lang not in ("en",):
                return True
    return False


def translate_terms(terms):
    if not terms:
        return {}

    results = {}
    for term in terms:
        translated = _translate_one(term)
        results[term] = translated
        time.sleep(0.05)

    return results


def _translate_one(term, retries=2):
    for attempt in range(retries + 1):
        try:
            translator = GoogleTranslator(source="auto", target="en")
            result = translator.translate(term)
            return result if result else ""
        except Exception:
            if attempt < retries:
                time.sleep(0.3)
    return ""
