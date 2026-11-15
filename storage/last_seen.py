"""Turn a last-seen row into the one sentence the wearer hears (SPEC.md section 4.10).

Every sentence comes in the five languages of contracts/languages.py. English
is the SPEC wording, byte for byte. The other languages are fixed, offline
tables: machine-drafted, short for speech, to be reviewed by a native speaker.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from storage._deps import DEFAULT_LANGUAGE, known_language, translate_label

NOT_SEEN = "I have not seen that."  # only for a query that ran and matched nothing
UNAVAILABLE = "Touch history is unavailable right now."  # database down or query failed

# Language code -> the no-match sentence.
NOT_SEEN_BY_LANGUAGE: dict[str, str] = {
    "en": NOT_SEEN,
    "zh": "我没有见过它。",
    "es": "No lo he visto.",
    "fr": "Je ne l'ai pas vu.",
    "hi": "मैंने वह नहीं देखा।",
}

# Language code -> the history-down sentence.
UNAVAILABLE_BY_LANGUAGE: dict[str, str] = {
    "en": UNAVAILABLE,
    "zh": "暂时无法查看触摸记录。",
    "es": "El historial de toques no está disponible ahora.",
    "fr": "L'historique des contacts est indisponible pour le moment.",
    "hi": "छूने का इतिहास अभी उपलब्ध नहीं है।",
}

# Language code -> time phrases. "one_*" is the singular; "*" takes {n}.
_AGO: dict[str, dict[str, str]] = {
    "en": {"now": "just now", "one_min": "1 minute ago", "min": "{n} minutes ago",
           "one_hour": "1 hour ago", "hour": "{n} hours ago"},
    "zh": {"now": "刚才", "one_min": "1分钟前", "min": "{n}分钟前",
           "one_hour": "1小时前", "hour": "{n}小时前"},
    "es": {"now": "hace un momento", "one_min": "hace 1 minuto", "min": "hace {n} minutos",
           "one_hour": "hace 1 hora", "hour": "hace {n} horas"},
    "fr": {"now": "à l'instant", "one_min": "il y a 1 minute", "min": "il y a {n} minutes",
           "one_hour": "il y a 1 heure", "hour": "il y a {n} heures"},
    "hi": {"now": "अभी-अभी", "one_min": "1 मिनट पहले", "min": "{n} मिनट पहले",
           "one_hour": "1 घंटा पहले", "hour": "{n} घंटे पहले"},
}

# Language code -> how a sentence is put together.
#   sep: between the parts; list_sep / and: joining neighbours;
#   next_to: the neighbours phrase; end: the closing punctuation.
_GRAMMAR: dict[str, dict[str, str]] = {
    "en": {"sep": ", ", "list_sep": ", ", "and": " and ", "next_to": "next to {x}", "end": "."},
    "zh": {"sep": "，", "list_sep": "、", "and": "和", "next_to": "在{x}旁边", "end": "。"},
    "es": {"sep": ", ", "list_sep": ", ", "and": " y ", "next_to": "junto a {x}", "end": "."},
    "fr": {"sep": ", ", "list_sep": ", ", "and": " et ", "next_to": "à côté de {x}", "end": "."},
    "hi": {"sep": ", ", "list_sep": ", ", "and": " और ", "next_to": "{x} के पास", "end": "।"},
}

_MINUTE = 60.0
_HOUR = 3600.0


def not_seen(language: str = DEFAULT_LANGUAGE) -> str:
    """Return the no-match sentence in language (English for an unknown code)."""
    return NOT_SEEN_BY_LANGUAGE[known_language(language)]


def unavailable(language: str = DEFAULT_LANGUAGE) -> str:
    """Return the history-unavailable sentence in language (English for an unknown code)."""
    return UNAVAILABLE_BY_LANGUAGE[known_language(language)]


def _ago(seconds: float, language: str = DEFAULT_LANGUAGE) -> str:
    """Return "just now", "N minutes ago" or "N hours ago" for an age in seconds."""
    words = _AGO[known_language(language)]
    if seconds < _MINUTE:
        return words["now"]
    if seconds < _HOUR:
        n = int(seconds // _MINUTE)
        return words["one_min"] if n == 1 else words["min"].format(n=n)
    n = int(seconds // _HOUR)
    return words["one_hour"] if n == 1 else words["hour"].format(n=n)


def join_names(names: Sequence[str], language: str = DEFAULT_LANGUAGE) -> str:
    """Join names as "a", "a and b" or "a, b and c"."""
    grammar = _GRAMMAR[known_language(language)]
    items = [n for n in (s.strip() for s in names) if n]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{grammar['list_sep'].join(items[:-1])}{grammar['and']}{items[-1]}"


def format_answer(
    row: Mapping[str, Any] | None, now: float, language: str = DEFAULT_LANGUAGE
) -> str:
    """Build the spoken answer for a last-seen row, or the no-match sentence, in language.

    A known class label (as object or neighbour) is translated; a Grok name is
    spoken as stored.
    """
    lang = known_language(language)
    if row is None:
        return not_seen(lang)
    label = (row.get("name") or "").strip() or (row.get("class_label") or "").strip()
    if not label:
        return not_seen(lang)
    grammar = _GRAMMAR[lang]
    parts = [translate_label(label, lang), _ago(now - float(row["ts"]), lang)]
    neighbours = join_names(
        [translate_label(n.strip(), lang) for n in (row.get("neighbours") or [])], lang
    )
    if neighbours:
        parts.append(grammar["next_to"].format(x=neighbours))
    return grammar["sep"].join(parts) + grammar["end"]
