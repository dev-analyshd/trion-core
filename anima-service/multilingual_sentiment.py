"""Multilingual Sentiment Analysis for ANIMA Engine.

Supports 10 languages using Unicode script detection and lexicon-based scoring.
Replaces the English-only VADER approach with broader language coverage.
"""
import re, unicodedata
from typing import Tuple

# ============================================================================
# Language lexicons (positive/negative words per language)
# ============================================================================

LEXICONS = {
    "en": {
        "positive": {"bullish", "surge", "rally", "gain", "growth", "adoption", "breakthrough", "partnership", "launch", "upgrade", "secure", "innovation", "support", "approve", "strong", "bull"},
        "negative": {"bearish", "crash", "hack", "exploit", "breach", "loss", "decline", "drop", "fraud", "scam", "rug", "dump", "bear", "ban", "reject", "fail"},
    },
    "zh": {
        "positive": {"上涨", "牛市", "增长", "突破", "合作", "启动", "升级", "安全", "创新", "支持", "批准", "强势"},
        "negative": {"下跌", "熊市", "崩溃", "黑客", "漏洞", "损失", "下降", "欺诈", "骗局", "砸盘", "禁止", "拒绝"},
    },
    "ja": {
        "positive": {"上昇", "強気", "成長", "突破", "提携", "開始", "アップグレード", "安全", "革新", "支持", "承認"},
        "negative": {"下落", "弱気", "崩壊", "ハッキング", "脆弱性", "損失", "減少", "詐欺", "廃止", "禁止", "拒否"},
    },
    "ko": {
        "positive": {"상승", "강세", "성장", "돌파", "파트너십", "출시", "업그레이드", "안전", "혁신", "지원", "승인"},
        "negative": {"하락", "약세", "붕괴", "해킹", "취약점", "손실", "감소", "사기", "폐지", "금지", "거부"},
    },
    "es": {
        "positive": {"alcista", "aumento", "crecimiento", "avance", "asociacion", "lanzamiento", "actualizacion", "seguro", "innovacion", "apoyo", "aprobado"},
        "negative": {"bajista", "caida", "colapso", "pirata", "brecha", "perdida", "declive", "fraude", "estafa", "prohibido", "rechazado"},
    },
    "fr": {
        "positive": {"haussier", "hausse", "croissance", "percee", "partenariat", "lancement", "mise_a_jour", "securise", "innovation", "soutien", "approuve"},
        "negative": {"baissier", "chute", "effondrement", "piratage", "breche", "perte", "declin", "fraude", "arnaque", "interdit", "rejete"},
    },
    "de": {
        "positive": {"bullisch", "anstieg", "wachstum", "durchbruch", "partnerschaft", "start", "aktualisierung", "sicher", "innovation", "unterstutzung", "genehmigt"},
        "negative": {"baerisch", "absturz", "zusammenbruch", "hack", "verlust", "ruckgang", "betrug", "betrug", "verboten", "abgelehnt"},
    },
    "ru": {
        "positive": {"бычий", "рост", "прорыв", "партнерство", "запуск", "обновление", "безопасный", "инновация", "поддержка", "одобрено"},
        "negative": {"медвежий", "падение", "крах", "взлом", "потеря", "спад", "мошенничество", "запрещено", "отклонено"},
    },
    "ar": {
        "positive": {"صعودي", "نمو", "اختراق", "شراكة", "إطلاق", "تحديث", "آمن", "ابتكار", "دعم", "موافق"},
        "negative": {"هبوطي", "سقوط", "انهيار", "اختراق", "خسارة", "انخفاض", "احتيال", "محظور", "مرفوض"},
    },
    "pt": {
        "positive": {"altista", "aumento", "crescimento", "avanco", "parceria", "lancamento", "atualizacao", "seguro", "inovacao", "apoio", "aprovado"},
        "negative": {"baixista", "queda", "colapso", "hack", "perda", "declinio", "fraude", "golpe", "proibido", "rejeitado"},
    },
}

# ============================================================================
# Language detection via Unicode script ranges
# ============================================================================

def detect_language(text: str) -> str:
    """Detect language from text using Unicode script analysis."""
    if not text:
        return "en"
    
    # Count characters by script
    cjk = 0
    hiragana = 0
    hangul = 0
    cyrillic = 0
    arabic = 0
    latin = 0
    
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF:
            cjk += 1
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            hiragana += 1
        elif 0xAC00 <= cp <= 0xD7AF:
            hangul += 1
        elif 0x0400 <= cp <= 0x04FF:
            cyrillic += 1
        elif 0x0600 <= cp <= 0x06FF:
            arabic += 1
        elif 0x0041 <= cp <= 0x024F:
            latin += 1
    
    if hiragana > 0:
        return "ja"
    if hangul > 0:
        return "ko"
    if cjk > 0:
        return "zh"
    if cyrillic > 0:
        return "ru"
    if arabic > 0:
        return "ar"
    
    # For Latin, try to distinguish by accent patterns
    # Default to English
    return "en"

# ============================================================================
# Sentiment computation
# ============================================================================

def compute_sentiment(text: str, lang: str = None) -> Tuple[float, str]:
    """
    Compute sentiment score for text in any supported language.
    
    Returns:
        (score, language) where score is 0.0 (very negative) to 1.0 (very positive),
        0.5 = neutral. Language is the detected/used language code.
    """
    if not text:
        return 0.5, "en"
    
    if lang is None:
        lang = detect_language(text)
    
    lexicon = LEXICONS.get(lang, LEXICONS["en"])
    
    # Tokenize: split on non-word boundaries
    # For CJK, each character is a token
    if lang in ("zh", "ja"):
        tokens = set(text.lower())
    else:
        tokens = set(re.findall(r'\w+', text.lower()))
    
    pos = len(tokens & lexicon["positive"])
    neg = len(tokens & lexicon["negative"])
    
    if pos + neg == 0:
        return 0.5, lang
    
    score = pos / (pos + neg)
    return score, lang

def analyze_multilingual(texts: list) -> dict:
    """
    Analyze a list of texts across multiple languages.
    
    Returns aggregated sentiment with language breakdown.
    """
    results = []
    lang_counts = {}
    
    for text in texts:
        score, lang = compute_sentiment(text)
        results.append({"score": score, "language": lang})
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    
    if not results:
        return {"avg_sentiment": 0.5, "languages": {}, "count": 0}
    
    avg = sum(r["score"] for r in results) / len(results)
    
    return {
        "avg_sentiment": avg,
        "sentiment_label": "positive" if avg > 0.6 else "negative" if avg < 0.4 else "neutral",
        "languages": lang_counts,
        "count": len(results),
        "supported_languages": list(LEXICONS.keys()),
        "results": results[:10],
    }

if __name__ == "__main__":
    # Test with multiple languages
    test_texts = [
        "Bitcoin surges to new high as institutional adoption grows",
        "比特币突破历史新高，机构采用率持续增长",
        "ビットコインが史上最高値を更新、機関の導入が拡大",
        "비트코인 상승, 기관 투자자 유입 증가",
        "Bitcoin cae por temor a hackeo masivo",
        "Le Bitcoin chute après un piratage massif",
    ]
    for text in test_texts:
        score, lang = compute_sentiment(text)
        print(f"[{lang}] score={score:.2f} | {text[:60]}")
    
    print("\nAggregated:", analyze_multilingual(test_texts))
