"""Redaction for capture data, using prove.py's SECRET_PATTERNS so cards and receipts share one rule set."""
import importlib.util
import os
import re
import urllib.parse

_PROVE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "prove.py")
_spec = importlib.util.spec_from_file_location("prove_it_core", _PROVE)
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

MASK = "<redacted>"


def text(value):
    return _core.redact(value)


def scrub(value, keys=()):
    """Mask values under any key in `keys`, and secret patterns in every string."""
    keys = set(keys)
    if isinstance(value, dict):
        return {k: (MASK if k in keys else scrub(v, keys)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, keys) for v in value]
    if isinstance(value, str):
        return text(value)
    return value


AUTH_KEY_RE = re.compile(r"(?i)(password|passwd|secret|token|cookie|session|api[_-]?key|credential|bearer|jwt|csrf|"
                         r"xsrf|signature|private[_-]?key|authorization|^auth$|^sid$|^pass$|^pwd$)")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")


def _url(value):
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not (parts.query or parts.password):
        return value
    query = urllib.parse.urlencode([(k, MASK if AUTH_KEY_RE.search(k) else v)
                                    for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)], safe="<>")
    netloc = parts.netloc.replace(f":{parts.password}@", f":{MASK}@") if parts.password else parts.netloc
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def auth(value, keys=()):
    """Mask auth-looking values: values under keys that look like auth (token, cookie, session, ...),
    URL query values with such names, URL passwords, JWTs, and the shared secret patterns."""
    keys = set(keys)
    if isinstance(value, dict):
        return {k: (MASK if (k in keys or AUTH_KEY_RE.search(str(k))) and isinstance(v, (str, int, float)) and not isinstance(v, bool)
                    else auth(v, keys)) for k, v in value.items()}
    if isinstance(value, list):
        return [auth(v, keys) for v in value]
    if isinstance(value, str):
        return text(JWT_RE.sub(MASK, _url(value)))
    return value
