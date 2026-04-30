#!/usr/bin/env python3
"""
Smore Labs / Spirit Library — Daily Growth Ops Check
Runs daily at 8am via launchd. Checks infrastructure health and sends HTML email via Resend.
"""

import socket
import subprocess
import datetime
import os
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/Documents/cmo-agent/logs/growth_ops.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

def _load_env_from_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

_load_env_from_dotenv()

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
RECIPIENT = "claudesonnet111@gmail.com"
POSTHOG_API_KEY = "phc_2kdEgAGWKAIxO5UeSuf458GSoCucw0SjcVBK7Esmu5T"
POSTHOG_HOST = "https://eu.posthog.com"

# Known Cloudflare IP prefixes
CLOUDFLARE_PREFIXES = [
    "104.16.", "104.17.", "104.18.", "104.19.", "104.20.", "104.21.", "104.22.", "104.23.", "104.24.",
    "172.64.", "172.65.", "172.66.", "172.67.",
    "162.159.", "141.101.", "108.162.", "190.93.", "188.114.",
    "197.234.", "198.41.", "103.21.", "103.22.", "103.31.",
]


def check_dns():
    """Check DNS resolution for spiritlibrary.app"""
    try:
        ips = socket.getaddrinfo("spiritlibrary.app", 443)
        resolved_ips = list(set(addr[4][0] for addr in ips))
        is_cloudflare = any(
            ip.startswith(prefix) for ip in resolved_ips for prefix in CLOUDFLARE_PREFIXES
        )
        return {
            "ok": True,
            "ips": resolved_ips,
            "cloudflare": is_cloudflare,
            "detail": f"Resolves to {', '.join(resolved_ips[:3])} {'(Cloudflare)' if is_cloudflare else '(NOT Cloudflare)'}",
        }
    except Exception as e:
        log.error(f"DNS check failed: {e}")
        return {"ok": False, "detail": str(e)}


def check_http(url):
    """Check HTTP status of a URL"""
    try:
        import urllib.request
        import ssl

        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "SmoreLabs-GrowthOps/1.0")
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        status = resp.getcode()
        return {
            "ok": status < 400,
            "status": status,
            "detail": f"HTTP {status}",
        }
    except Exception as e:
        log.error(f"HTTP check failed for {url}: {e}")
        # Try GET if HEAD fails
        try:
            import urllib.request
            import ssl

            ctx = ssl.create_default_context()
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "SmoreLabs-GrowthOps/1.0")
            resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            status = resp.getcode()
            return {"ok": status < 400, "status": status, "detail": f"HTTP {status} (GET fallback)"}
        except Exception as e2:
            return {"ok": False, "detail": str(e2)}


def check_eas_builds():
    """Check last modified time of eas.json as proxy for recent builds"""
    try:
        eas_path = Path.home() / "Documents" / "spiritlibrary-mobile" / "eas.json"
        if not eas_path.exists():
            return {"ok": False, "detail": "eas.json not found"}
        mtime = datetime.datetime.fromtimestamp(eas_path.stat().st_mtime)
        age = datetime.datetime.now() - mtime
        days_ago = age.days
        return {
            "ok": days_ago < 7,
            "detail": f"Last modified {mtime.strftime('%Y-%m-%d %H:%M')} ({days_ago}d ago)",
        }
    except Exception as e:
        log.error(f"EAS check failed: {e}")
        return {"ok": False, "detail": str(e)}


def check_posthog():
    """Check PostHog for events in last 24h — requires Personal API key"""
    personal_key = os.environ.get("POSTHOG_PERSONAL_API_KEY", "")
    if not personal_key:
        return {
            "ok": None,
            "detail": "Skipped — set POSTHOG_PERSONAL_API_KEY env var (get from eu.posthog.com → Settings → Personal API Keys)",
        }
    try:
        import urllib.request
        import json as _json

        url = f"{POSTHOG_HOST}/api/projects/"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {personal_key}")
        resp = urllib.request.urlopen(req, timeout=15)
        data = _json.loads(resp.read())

        if "results" in data and len(data["results"]) > 0:
            project_id = data["results"][0].get("id")
            events_url = f"{POSTHOG_HOST}/api/projects/{project_id}/events/?limit=1"
            req2 = urllib.request.Request(events_url)
            req2.add_header("Authorization", f"Bearer {personal_key}")
            resp2 = urllib.request.urlopen(req2, timeout=15)
            events_data = _json.loads(resp2.read())
            count = len(events_data.get("results", []))
            has_events = count > 0
            return {
                "ok": has_events,
                "detail": f"{'Events received' if has_events else 'No events'} in last 24h (project {project_id})",
            }
        return {"ok": False, "detail": "No projects found in PostHog"}
    except Exception as e:
        log.error(f"PostHog check failed: {e}")
        return {"ok": False, "detail": str(e)}


def build_html(results):
    """Build HTML email from check results"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def status_dot(ok):
        if ok is None:
            color = "#f59e0b"  # yellow for skipped
        else:
            color = "#22c55e" if ok else "#ef4444"
        return f'<span style="color:{color};font-size:20px;">&#9679;</span>'

    rows = ""
    for name, result in results.items():
        rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{status_dot(result['ok'])}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:600;">{name}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;">{result['detail']}</td>
        </tr>"""

    all_ok = all(r["ok"] for r in results.values() if r["ok"] is not None)
    summary_color = "#22c55e" if all_ok else "#ef4444"
    summary_text = "All systems operational" if all_ok else "Issues detected"

    html = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
    <h2 style="margin-bottom:4px;">Smore Labs — Growth Ops Daily</h2>
    <p style="color:#666;margin-top:0;">{now}</p>
    <p style="background:{summary_color}22;border-left:4px solid {summary_color};padding:10px 14px;border-radius:4px;">
        <strong style="color:{summary_color};">{summary_text}</strong>
    </p>
    <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="text-align:left;">
            <th style="padding:8px 12px;border-bottom:2px solid #ddd;width:30px;"></th>
            <th style="padding:8px 12px;border-bottom:2px solid #ddd;">Check</th>
            <th style="padding:8px 12px;border-bottom:2px solid #ddd;">Detail</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <p style="color:#999;font-size:12px;margin-top:24px;">Sent by growth_ops_check.py via Resend</p>
    </body></html>"""
    return html


def send_email(html):
    """Send email via Resend API using curl (matches working pm_report.py pattern)"""
    payload = json.dumps({
        "from": "Growth Ops <onboarding@resend.dev>",
        "to": [RECIPIENT],
        "subject": f"Growth Ops Report — {datetime.datetime.now().strftime('%b %d')}",
        "html": html,
    })

    tmp = Path("/tmp/growth_ops_payload.json")
    tmp.write_text(payload)

    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://api.resend.com/emails",
        "-H", f"Authorization: Bearer {RESEND_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", f"@{tmp}",
    ], capture_output=True, text=True)

    if result.returncode == 0 and '"id"' in result.stdout:
        log.info(f"Email sent: {result.stdout.strip()}")
        return True
    else:
        log.error(f"Failed to send email: {result.stdout} {result.stderr}")
        return False


def main():
    log.info("Starting Growth Ops check...")

    results = {}

    # 1. DNS
    results["DNS: spiritlibrary.app"] = check_dns()

    # 2. HTTP main site
    results["HTTP: spiritlibrary.app"] = check_http("https://spiritlibrary.app")

    # 3. HTTP Cloudflare Pages fallback
    results["HTTP: Pages fallback"] = check_http("https://spiritlibrary-app.pages.dev")

    # 4. EAS builds
    results["EAS Builds (eas.json)"] = check_eas_builds()

    # 5. PostHog events
    results["PostHog Events (24h)"] = check_posthog()

    # Build and send
    html = build_html(results)
    sent = send_email(html)

    status = "sent" if sent else "FAILED to send"
    log.info(f"Growth Ops check complete. Email {status}.")


if __name__ == "__main__":
    main()
