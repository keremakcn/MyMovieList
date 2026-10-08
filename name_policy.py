"""Small TR/EN profile-name policy. Personal movie notes are never filtered."""

import re
import unicodedata

# Long, distinctive roots can be matched through digits/underscores. Short
# words use token boundaries so ordinary names such as Nazim/Scunthorpe survive.
BLOCKED_ROOTS = (
    "hitler",
    "motherfucker",
    "orospu",
    "siktir",
    "sikeyim",
    "sikim",
    "yarrak",
    "yarak",
    "amcik",
    "gotveren",
    "nigger",
    "faggot",
)
BLOCKED_TOKENS = frozenset(
    (
        "nazi",
        "nazis",
        "nazism",
        "nazifan",
        "fuck",
        "fucking",
        "fucker",
        "fuckoff",
        "fuckyou",
        "fuckhead",
        "shit",
        "shitty",
        "shithead",
        "bitch",
        "bitchboy",
        "bastard",
        "asshole",
        "cunt",
        "dick",
        "dickhead",
        "pussy",
        "amk",
        "aq",
        "sik",
    )
)
LEET = str.maketrans("0134578", "oieastb")


def name_allowed(value):
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKD", value).lower().replace("ı", "i")
    normalized = "".join(c for c in normalized if not "\u0300" <= c <= "\u036f")
    normalized = re.sub("[^a-z0-9]+", "_", normalized)
    # Match both normal text and common numeric substitutions.
    for candidate in (normalized, normalized.translate(LEET)):
        compact = candidate.replace("_", "")
        if any(root in compact for root in BLOCKED_ROOTS):
            return False
        tokens = re.sub("[0-9]+", "_", candidate).strip("_").split("_")
        if BLOCKED_TOKENS.intersection(tokens) or compact in BLOCKED_TOKENS:
            return False
    return True


def require_allowed_name(value):
    if not name_allowed(value):
        raise ValueError("This name is not allowed. Choose another one.")
    return value
