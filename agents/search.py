"""
Unified search wrapper. Free-first cascade:

    1. Brave Search API   — 2000 free queries/mo, BRAVE_SEARCH_API_KEY
    2. Exa neural search  — paid, EXA_API_KEY (better for "find me articles like X")
    3. Claude + web_search — only if both above unkeyed (uses Anthropic credits)

Returns a uniform list of {title, url, snippet, published_at?} dicts.

Design notes:
- The Brave path is lexical (good for breaking news, named entities).
- The Exa path is neural (good for thematic / "more like this" queries).
- Caller can hint via `mode="neural"` to prefer Exa first.
- All providers fail open: if Brave is keyed but rate-limited, we fall through
  rather than raising. The caller decides how to handle empty results.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Literal, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

SearchMode = Literal["lexical", "neural", "auto"]


def _brave(query: str, n: int = 10) -> list[dict]:
    key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not key:
        return []
    url = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={n}"
    req = Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
    try:
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, ValueError):
        return []
    web = (data.get("web") or {}).get("results") or []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", ""),
            "published_at": r.get("age"),
            "provider": "brave",
        }
        for r in web[:n]
    ]


def _exa(query: str, n: int = 10, mode: str = "neural") -> list[dict]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return []
    body = json.dumps({
        "query": query,
        "numResults": n,
        "type": mode,           # "neural" | "keyword"
        "contents": {"text": {"maxCharacters": 500}},
    }).encode("utf-8")
    req = Request(
        "https://api.exa.ai/search",
        data=body,
        headers={"Content-Type": "application/json", "x-api-key": key},
    )
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, ValueError):
        return []
    results = data.get("results") or []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("text") or "")[:500],
            "published_at": r.get("publishedDate"),
            "provider": "exa",
        }
        for r in results[:n]
    ]


def search(query: str, n: int = 10, mode: SearchMode = "auto") -> list[dict]:
    """Run a search. `mode='neural'` prefers Exa; default tries Brave first."""
    if mode == "neural":
        out = _exa(query, n=n, mode="neural")
        if out:
            return out
        return _brave(query, n=n)

    out = _brave(query, n=n)
    if out:
        return out
    return _exa(query, n=n, mode="neural" if mode == "auto" else "keyword")


def has_provider() -> bool:
    """True if at least one search provider is keyed. Callers can use this to
    decide whether to short-circuit to existing Claude+web_search behavior."""
    return bool(os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("EXA_API_KEY"))


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "cocktail trends 2026"
    for r in search(q, n=5):
        print(f"[{r['provider']}] {r['title']}\n  {r['url']}\n  {r['snippet'][:160]}\n")
