"""Keep optional parameter annotations owned by QGIS, preserving fallback notes."""

import re


def optional_description(description, locale="en"):
    value = str(description)
    replacement = {"en": "may be blank if", "es": "puede quedar vacío si",
                   "pt": "pode ficar vazio se"}[locale]
    value = re.sub(r"\b(?:optional if|opcional si|opcional se)\b", replacement, value, flags=re.I)
    value = re.sub(r"\(\s*(?:optional|opcional)\s*\)", "", value, flags=re.I)
    value = re.sub(r"\b(?:optional|opcional)\s*[;,]\s*", "", value, flags=re.I)
    value = re.sub(r"[,;]\s*(?:optional|opcional)\b", "", value, flags=re.I)
    value = re.sub(r"\b(?:optional|opcional)\b", "", value, flags=re.I)
    return re.sub(r" {2,}", " ", value).strip()
