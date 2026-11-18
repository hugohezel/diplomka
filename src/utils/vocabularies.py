"""Controlled vocabulary data used by translation-layer operators."""

from typing import Any

from .checks import normalize_text


# OECD Fields of Science and Technology, 2007 classification.
FOS = {
    "1": "Natural sciences",
    "1.1": "Mathematics",
    "1.2": "Computer and information sciences",
    "1.3": "Physical sciences",
    "1.4": "Chemical sciences",
    "1.5": "Earth and related environmental sciences",
    "1.6": "Biological sciences",
    "1.7": "Other natural sciences",
    "2": "Engineering and technology",
    "2.1": "Civil engineering",
    "2.2": "Electrical engineering, electronic engineering, information engineering",
    "2.3": "Mechanical engineering",
    "2.4": "Chemical engineering",
    "2.5": "Materials engineering",
    "2.6": "Medical engineering",
    "2.7": "Environmental engineering",
    "2.8": "Environmental biotechnology",
    "2.9": "Industrial biotechnology",
    "2.10": "Nanotechnology",
    "2.11": "Other engineering and technologies",
    "3": "Medical and health sciences",
    "3.1": "Basic medicine",
    "3.2": "Clinical medicine",
    "3.3": "Health sciences",
    "3.4": "Medical biotechnology",
    "3.5": "Other medical sciences",
    "4": "Agricultural sciences",
    "4.1": "Agriculture, forestry and fisheries",
    "4.2": "Animal and dairy science",
    "4.3": "Veterinary science",
    "4.4": "Agricultural biotechnology",
    "4.5": "Other agricultural sciences",
    "5": "Social sciences",
    "5.1": "Psychology",
    "5.2": "Economics and business",
    "5.3": "Educational sciences",
    "5.4": "Sociology",
    "5.5": "Law",
    "5.6": "Political science",
    "5.7": "Social and economic geography",
    "5.8": "Media and communications",
    "5.9": "Other social sciences",
    "6": "Humanities",
    "6.1": "History and archaeology",
    "6.2": "Languages and literature",
    "6.3": "Philosophy, ethics and religion",
    "6.4": "Arts",
    "6.5": "Other humanities",
}


def fos_match(term: Any) -> str | None:
    text = normalize_text(term).removeprefix("fos: ").removeprefix("fos:").strip()
    for code, label in FOS.items():
        if text in {code, normalize_text(label)}:
            return code
    return None
