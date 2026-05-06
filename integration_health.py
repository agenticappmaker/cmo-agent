"""
Smore Labs integration healthcheck.

Pings every paid + free integration we depend on with the cheapest possible
status check. Reports which keys are present, which are reachable, and
flags free-tier quota signals.

Run:
    python3 integration_health.py             # human-readable
    python3 integration_health.py --json      # machine-readable
    python3 integration_health.py --email     # ship a digest to OPS_EMAIL via Resend

Designed to be wired into a daily launchd job after the morning outreach
triage. Fails open: a single integration outage doesn't fail the run; the
report shows red on that row and continues.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _load_env_file(path: Path) -> None:
    """Lightweight .env loader so the script works under cron/launchd without
    a shell `source` step. Won't override pre-existing env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_file(Path(__file__).resolve().parent / ".env")

OPS_EMAIL = os.environ.get("OPS_EMAIL", "claudesonnet111@gmail.com")


@dataclass
class CheckResult:
    name: str
    keyed: bool
    ok: bool
    detail: str
    elapsed_ms: int


def _http(req: Request, timeout: float = 6) -> tuple[int, str]:
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(2048).decode("utf-8", errors="replace")
    except HTTPError as e:
        body = ""
        try:
            body = e.read(1024).decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body
    except (URLError, OSError) as e:
        return 0, str(e)


def _t(fn, name: str, env_keys: list[str]) -> CheckResult:
    keyed = all(os.environ.get(k) for k in env_keys)
    if not keyed:
        missing = [k for k in env_keys if not os.environ.get(k)]
        return CheckResult(name, False, False, f"missing env: {', '.join(missing)}", 0)
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"exception: {e}"
    return CheckResult(name, True, ok, detail, int((time.time() - t0) * 1000))


# ---------- individual checks ----------

def check_abstract() -> tuple[bool, str]:
    key = os.environ["ABSTRACT_API_KEY"]
    code, body = _http(Request(
        f"https://emailreputation.abstractapi.com/v1/?api_key={key}&email=ops@smorelabs.com"
    ))
    if code == 200:
        try:
            data = json.loads(body)
            status = (data.get("email_deliverability") or {}).get("status", "?")
            return True, f"status={status}"
        except Exception:
            return False, f"200 but bad JSON"
    if code == 422:
        return False, "422 quota burned"
    return False, f"HTTP {code}"


def check_brave() -> tuple[bool, str]:
    key = os.environ["BRAVE_SEARCH_API_KEY"]
    req = Request(
        "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": "smore labs", "count": 1}),
        headers={"Accept": "application/json", "X-Subscription-Token": key},
    )
    code, body = _http(req)
    if code == 200:
        return True, "ok"
    if code == 429:
        return False, "429 rate limit"
    return False, f"HTTP {code}"


def check_exa() -> tuple[bool, str]:
    key = os.environ["EXA_API_KEY"]
    req = Request(
        "https://api.exa.ai/search",
        method="POST",
        data=json.dumps({"query": "smore labs", "numResults": 1}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": key},
    )
    code, body = _http(req)
    return (code == 200, f"HTTP {code}")


def check_firecrawl() -> tuple[bool, str]:
    key = os.environ["FIRECRAWL_API_KEY"]
    req = Request(
        "https://api.firecrawl.dev/v1/scrape",
        method="POST",
        data=json.dumps({"url": "https://example.com", "formats": ["markdown"]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    code, body = _http(req, timeout=20)
    return (code == 200, f"HTTP {code}")


def check_browserbase() -> tuple[bool, str]:
    key = os.environ["BROWSERBASE_API_KEY"]
    proj = os.environ["BROWSERBASE_PROJECT_ID"]
    req = Request(
        f"https://api.browserbase.com/v1/projects/{proj}",
        headers={"x-bb-api-key": key},
    )
    code, _ = _http(req)
    return (code == 200, f"HTTP {code}")


def check_gladia() -> tuple[bool, str]:
    key = os.environ["GLADIA_API_KEY"]
    # No cheap status endpoint; just confirm auth works on a 405-able route.
    req = Request("https://api.gladia.io/v2/upload", headers={"x-gladia-key": key})
    code, _ = _http(req)
    # 405 (method not allowed on GET) or 400 means auth passed.
    return (code in (200, 400, 405), f"HTTP {code}")


def check_resend() -> tuple[bool, str]:
    key = os.environ["RESEND_API_KEY"]
    req = Request(
        "https://api.resend.com/domains",
        headers={"Authorization": f"Bearer {key}"},
    )
    code, _ = _http(req)
    # 200 = full access, 403 = valid key but scoped narrower (sending-only).
    # 401 = bad/revoked key.
    if code == 200:
        return True, "ok (full)"
    if code == 403:
        return True, "ok (sending-only scope)"
    return False, f"HTTP {code}"


def check_anthropic() -> tuple[bool, str]:
    key = os.environ["ANTHROPIC_API_KEY"]
    # Cheapest call: 1-token completion via messages API.
    req = Request(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        data=json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ok"}],
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    code, body = _http(req, timeout=15)
    if code == 200:
        return True, "ok"
    if code == 429:
        return False, "429 rate limit"
    if code == 401:
        return False, "401 auth"
    return False, f"HTTP {code}"


def check_openai() -> tuple[bool, str]:
    key = os.environ["OPENAI_API_KEY"]
    req = Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    code, _ = _http(req, timeout=8)
    return (code == 200, f"HTTP {code}")


def check_google_ai() -> tuple[bool, str]:
    key = os.environ["GOOGLE_AI_API_KEY"]
    req = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
    )
    code, _ = _http(req, timeout=8)
    return (code == 200, f"HTTP {code}")


def check_supabase() -> tuple[bool, str]:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not key:
        return False, "no key"
    req = Request(
        f"{url.rstrip('/')}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    code, _ = _http(req)
    return (code in (200, 401, 404), f"HTTP {code}")


# ---------- runner ----------

CHECKS = [
    ("Abstract Email Reputation", ["ABSTRACT_API_KEY"], check_abstract),
    ("Brave Search",              ["BRAVE_SEARCH_API_KEY"], check_brave),
    ("Exa Search",                ["EXA_API_KEY"], check_exa),
    ("Firecrawl",                 ["FIRECRAWL_API_KEY"], check_firecrawl),
    ("Browserbase",               ["BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID"], check_browserbase),
    ("Gladia",                    ["GLADIA_API_KEY"], check_gladia),
    ("Resend",                    ["RESEND_API_KEY"], check_resend),
    ("Anthropic Claude",          ["ANTHROPIC_API_KEY"], check_anthropic),
    ("OpenAI",                    ["OPENAI_API_KEY"], check_openai),
    ("Google AI (Imagen)",        ["GOOGLE_AI_API_KEY"], check_google_ai),
    ("Supabase",                  ["SUPABASE_URL"], check_supabase),
]


def run_all() -> list[CheckResult]:
    return [_t(fn, name, env_keys) for name, env_keys, fn in CHECKS]


def render_human(results: list[CheckResult]) -> str:
    lines = ["Smore Labs Integration Health", "-" * 60]
    keyed = sum(1 for r in results if r.keyed)
    ok = sum(1 for r in results if r.ok)
    lines.append(f"  keyed: {keyed}/{len(results)}    ok: {ok}/{keyed if keyed else 1}")
    lines.append("")
    for r in results:
        if not r.keyed:
            mark = "○"
        elif r.ok:
            mark = "✓"
        else:
            mark = "✗"
        lines.append(f"  {mark}  {r.name:30}  {r.detail:30}  {r.elapsed_ms}ms" if r.keyed else f"  {mark}  {r.name:30}  {r.detail}")
    return "\n".join(lines)


def render_email_body(results: list[CheckResult]) -> str:
    keyed = [r for r in results if r.keyed]
    failing = [r for r in keyed if not r.ok]
    head = f"Smore Labs integration health — {len(failing)} failing of {len(keyed)} keyed."
    if not failing:
        return head + " All clear."
    lines = [head, ""]
    lines.append("FAILING:")
    for r in failing:
        lines.append(f"  ✗ {r.name}: {r.detail} ({r.elapsed_ms}ms)")
    lines.append("")
    lines.append("KEYED + OK:")
    for r in keyed:
        if r.ok:
            lines.append(f"  ✓ {r.name}: {r.detail} ({r.elapsed_ms}ms)")
    unkeyed = [r for r in results if not r.keyed]
    if unkeyed:
        lines.append("")
        lines.append("NOT KEYED (skipped):")
        for r in unkeyed:
            lines.append(f"  ○ {r.name}: {r.detail}")
    return "\n".join(lines)


def email_via_resend(subject: str, body: str) -> bool:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        return False
    req = Request(
        "https://api.resend.com/emails",
        method="POST",
        data=json.dumps({
            "from": "Smore Ops <noreply@smorelabs.com>",
            "to": OPS_EMAIL,
            "subject": subject,
            "text": body,
        }).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    code, _ = _http(req, timeout=10)
    return code == 200


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON output for machines")
    p.add_argument("--email", action="store_true", help="Email digest to OPS_EMAIL via Resend")
    args = p.parse_args()

    results = run_all()

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print(render_human(results))

    if args.email:
        keyed = [r for r in results if r.keyed]
        failing = [r for r in keyed if not r.ok]
        subj = f"[ops] integrations: {len(failing)} failing of {len(keyed)} keyed"
        sent = email_via_resend(subj, render_email_body(results))
        print(f"\n[email digest sent: {sent}]")

    # Non-zero exit if any keyed integration is failing.
    failing = sum(1 for r in results if r.keyed and not r.ok)
    return 0 if failing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
