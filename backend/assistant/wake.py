"""
Finds "Vira" or "hey Vira" at the start of what someone said.

Speech-to-text has never heard of Vira, so the pattern also accepts the spellings
it tends to produce instead. The wake word only starts a conversation: it can't
approve anything.
"""

import re

_AUDIO_TAGS = re.compile(r'[\[(][^\])]*[\])]')
_WAKE = re.compile(
    r"^\W*(?:(?:um+|uh+|so|okay|ok|hey|hi|hello|yo|ay|a)\W+)*"
    r"(?:vira|vera|veera|vyra|viera|veira|vire|veerah|vyrah|virah|verah|wira|bira|mira)\b\W*",
    re.IGNORECASE,
)


def strip_wake_word(text):
    """Returns (heard, rest): whether the wake word was said, and the words after it."""
    cleaned = _AUDIO_TAGS.sub(' ', text).strip()
    match = _WAKE.match(cleaned)
    if match is None:
        return False, cleaned
    return True, cleaned[match.end():].strip()
