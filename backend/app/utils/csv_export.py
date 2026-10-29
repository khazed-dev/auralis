"""Keep untrusted CSV cells as text when opened in a spreadsheet."""
import unicodedata
from typing import Any, Iterable


def safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    # Detect width variants and whitespace-prefixed formulas without changing
    # the user's original text; csv.writer still handles quotes and delimiters.
    prefix = unicodedata.normalize("NFKC", text).lstrip(" ")
    if prefix.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def safe_csv_row(values: Iterable[Any]) -> list[str]:
    return [safe_csv_cell(value) for value in values]
