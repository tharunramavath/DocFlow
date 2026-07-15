from __future__ import annotations

import re
from typing import Dict, List

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_ ]+?)\s*\}\}")


def extract_placeholders(*texts: str) -> List[str]:
    """
    Extract unique placeholders from one or more strings.

    Example:
        Dear {{Name}}

        Welcome {{Organization}}

    returns

        ["{{Name}}", "{{Organization}}"]
    """

    found = []

    for text in texts:
        if not text:
            continue

        matches = PLACEHOLDER_PATTERN.findall(text)

        for m in matches:
            name = f"{{{{{m.strip()}}}}}"

            if name and name not in found:
                found.append(name)

    return found


def auto_map_placeholders(
    placeholders: List[str],
    excel_columns: List[str],
) -> Dict[str, str]:
    """
    Automatically map placeholders to excel columns
    by case-insensitive comparison.
    """

    mapping = {}

    normalized = {
        c.strip().lower(): c
        for c in excel_columns
    }

    for p in placeholders:
        key = p.strip("{} ").lower()

        if key in normalized:
            mapping[p] = normalized[key]

    return mapping


def replace_placeholders(
    text: str,
    context: Dict[str, str],
) -> str:
    """
    Replace every placeholder.

    Context keys should INCLUDE {{ }}

    Example

    context

    {
        "{{Name}}": "Sai",
        "{{Organization}}": "CBIT"
    }

    """

    if not text:
        return ""

    def repl(match):
        key = f"{{{{{match.group(1).strip()}}}}}"
        return str(context.get(key, match.group(0)))

    return PLACEHOLDER_PATTERN.sub(repl, text)


def merge_placeholder_mapping(
    detected: List[str],
    previous_mapping: Dict[str, str],
) -> Dict[str, str]:
    """
    Preserve previous mappings while adding newly detected placeholders.
    """

    result = {}

    previous_mapping = previous_mapping or {}

    for item in detected:
        result[item] = previous_mapping.get(item, "")

    return result