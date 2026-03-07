#!/usr/bin/env python3
"""
Austin Babe Radar
=================
Scrapes Eventbrite and Meetup for early-signal trendy Austin events that attract
hot single women — wellness pop-ups, run clubs, yoga, sound baths, brunches,
singles mixers — *before* they get flooded.

Sources (all free, no API key needed):
  • Eventbrite  — wellness & fitness events in Austin, sorted by date
  • Meetup      — women's wellness / fitness groups in Austin

Usage:
    python3 babe_radar.py               # scrape + open results in browser
    python3 babe_radar.py --save        # also save to CSV
    python3 babe_radar.py --email       # also email results to EMAIL_TO list
    python3 babe_radar.py --no-browser  # skip auto-opening browser
"""

import os
import re
import csv
import json
import smtplib
import argparse
import tempfile
import webbrowser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===========================================================================
# CONFIG
# ===========================================================================

TOP_N = 20  # how many results to show / export

# ---------------------------------------------------------------------------
# SMTP / Email (only needed if using --email)
# Get a Gmail App Password at: myaccount.google.com/apppasswords
# ---------------------------------------------------------------------------
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "your@gmail.com")       # your Gmail
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your_app_password")    # Gmail App Password

# List of recipients — add your friend's email as the second item
EMAIL_TO = [
    os.getenv("EMAIL_TO",       "your@gmail.com"),        # you
    os.getenv("EMAIL_TO_FRIEND", ""),                     # friend — set env var or edit here
]
# Filter out empty strings
EMAIL_TO = [e for e in EMAIL_TO if e and e != "your@gmail.com"]

# ---------------------------------------------------------------------------
# Shared browser-like headers to avoid basic bot blocks
# ---------------------------------------------------------------------------
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Keywords that signal female-forward / trendy events
SIGNAL_KEYWORDS = [
    "wellness", "yoga", "pilates", "hot pilates", "sound bath", "run club",
    "brunch", "mixer", "girls night", "ladies", "women", "empowerment",
    "barre", "meditation", "breathwork", "cycle", "spin", "hiit", "sculpt",
    "sober", "clean", "glow", "feminine", "sister", "sisterhood",
]


# ===========================================================================
# SOURCE 1: Eventbrite
# ===========================================================================

def scrape_eventbrite() -> list[dict]:
    results  = []
    seen_urls = set()

    search_urls = [
        "https://www.eventbrite.com/d/tx--austin/wellness/?sort=date",
        "https://www.eventbrite.com/d/tx--austin/fitness/?sort=date",
        "https://www.eventbrite.com/d/tx--austin/yoga/?sort=date",
    ]

    for url in search_urls:
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        except Exception as e:
            print(f"  [Eventbrite] Connection error: {e}")
            continue

        if resp.status_code != 200:
            print(f"  [Eventbrite] HTTP {resp.status_code} — {url}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Strategy 1: JSON-LD blocks
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") != "Event":
                        continue
                    event_url = item.get("url", "")
                    if event_url in seen_urls:
                        continue
                    seen_urls.add(event_url)

                    name        = item.get("name", "")
                    description = item.get("description", "")
                    start       = (item.get("startDate") or "")[:10]
                    location    = ""
                    loc = item.get("location", {})
                    if isinstance(loc, dict):
                        addr = loc.get("address", {})
                        if isinstance(addr, dict):
                            location = addr.get("addressLocality", "")

                    if not _is_relevant(name + " " + description):
                        continue

                    results.append({
                        "source":   "Eventbrite",
                        "date":     start,
                        "name":     name,
                        "text":     description[:300] if description else name,
                        "location": location or "Austin, TX",
                        "url":      event_url,
                    })
            except (json.JSONDecodeError, AttributeError):
                continue

        # Strategy 2: embedded JSON blobs with event arrays
        for script in soup.find_all("script"):
            raw = script.string or ""
            if "startDate" not in raw:
                continue
            for match in re.findall(r'"events"\s*:\s*(\[.*?\])', raw, re.DOTALL):
                try:
                    for e in json.loads(match):
                        event_url = e.get("url") or e.get("eventUrl", "")
                        if event_url in seen_urls:
                            continue
                        seen_urls.add(event_url)
                        name  = e.get("name") or e.get("title", "")
                        start = (e.get("startDate") or e.get("start_date") or "")[:10]
                        if not name or not _is_relevant(name):
                            continue
                        results.append({
                            "source":   "Eventbrite",
                            "date":     start,
                            "name":     name,
                            "text":     name,
                            "location": "Austin, TX",
                            "url":      event_url,
                        })
                except (json.JSONDecodeError, TypeError):
                    continue

    print(f"  [Eventbrite] {len(results)} relevant events")
    return results


# ===========================================================================
# SOURCE 2: Meetup
# ===========================================================================

def scrape_meetup() -> list[dict]:
    results   = []
    seen_urls = set()

    search_urls = [
        "https://www.meetup.com/find/events/?allMeetups=false&keywords=women+wellness&location=Austin+TX&radius=25",
        "https://www.meetup.com/find/events/?allMeetups=false&keywords=yoga+women&location=Austin+TX&radius=25",
        "https://www.meetup.com/find/events/?allMeetups=false&keywords=run+club+women&location=Austin+TX&radius=25",
    ]

    for url in search_urls:
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        except Exception as e:
            print(f"  [Meetup] Connection error: {e}")
            continue

        if resp.status_code != 200:
            print(f"  [Meetup] HTTP {resp.status_code}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") != "Event":
                        continue
                    event_url = item.get("url", "")
                    if event_url in seen_urls:
                        continue
                    seen_urls.add(event_url)

                    name        = item.get("name", "")
                    description = item.get("description", "")
                    start       = (item.get("startDate") or "")[:10]
                    organizer   = (item.get("organizer") or {}).get("name", "")

                    if not _is_relevant(name + " " + description):
                        continue

                    results.append({
                        "source":   "Meetup",
                        "date":     start,
                        "name":     name,
                        "text":     description[:300] if description else name,
                        "location": organizer or "Austin, TX",
                        "url":      event_url,
                    })
            except (json.JSONDecodeError, AttributeError):
                continue

        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            try:
                nd = json.loads(next_data_tag.string or "")
                _extract_meetup_next_data(nd, results, seen_urls)
            except (json.JSONDecodeError, AttributeError):
                pass

    print(f"  [Meetup]     {len(results)} relevant events")
    return results


def _extract_meetup_next_data(obj, results: list, seen_urls: set, depth: int = 0) -> None:
    if depth > 10:
        return
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("name", "")
        url   = obj.get("eventUrl") or obj.get("link") or obj.get("url", "")
        date  = (obj.get("dateTime") or obj.get("startDate") or obj.get("date") or "")[:10]
        if title and url and url not in seen_urls and _is_relevant(title):
            seen_urls.add(url)
            results.append({
                "source":   "Meetup",
                "date":     date,
                "name":     title,
                "text":     obj.get("description", title)[:300],
                "location": "Austin, TX",
                "url":      url,
            })
        for v in obj.values():
            _extract_meetup_next_data(v, results, seen_urls, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _extract_meetup_next_data(item, results, seen_urls, depth + 1)


# ===========================================================================
# HELPERS
# ===========================================================================

def _is_relevant(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in SIGNAL_KEYWORDS)


def aggregate(sources: list[list[dict]]) -> list[dict]:
    combined, seen = [], set()
    for source in sources:
        for item in source:
            url = item.get("url", "")
            if url and url in seen:
                continue
            seen.add(url)
            combined.append(item)
    combined.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)
    return combined


# ===========================================================================
# OUTPUT 1: HTML page (auto-opens in browser)
# ===========================================================================

def build_html(events: list[dict]) -> str:
    date_str    = datetime.now().strftime("%B %d, %Y  %I:%M %p")
    source_badge = {
        "Eventbrite": ("#f05537", "white"),
        "Meetup":     ("#f65858", "white"),
    }

    cards_html = ""
    if not events:
        cards_html = """
        <div class="empty">
            No events found right now.<br>
            Eventbrite and Meetup may be JS-rendered — try the manual links below.
        </div>"""
    else:
        for e in events[:TOP_N]:
            name      = e.get("name") or ""
            date      = e.get("date") or "date unknown"
            location  = e.get("location") or "Austin, TX"
            text      = e.get("text") or ""
            url       = e.get("url") or "#"
            source    = e.get("source") or ""
            bg, fg    = source_badge.get(source, ("#888", "white"))
            # trim description if it repeats the title
            desc = text if text.lower().strip() != name.lower().strip() else ""

            cards_html += f"""
        <a class="card" href="{url}" target="_blank" rel="noopener">
            <div class="card-top">
                <span class="badge" style="background:{bg};color:{fg}">{source}</span>
                <span class="date">{date}</span>
            </div>
            <div class="card-title">{name}</div>
            <div class="card-location">📍 {location}</div>
            {"<div class='card-desc'>" + desc[:200] + ("…" if len(desc) > 200 else "") + "</div>" if desc else ""}
        </a>"""

    manual = """
        <div class="manual">
            <h3>Always worth a manual check</h3>
            <ul>
                <li><a href="https://www.eventbrite.com/d/tx--austin/wellness/?sort=date" target="_blank">Eventbrite → Austin Wellness (sort: Date)</a></li>
                <li><a href="https://www.meetup.com/find/events/?allMeetups=false&keywords=women+wellness&location=Austin+TX&radius=25" target="_blank">Meetup → Women + Wellness near Austin</a></li>
                <li><a href="https://sweatpals.com" target="_blank">Sweatpals.com — ladies-only ATX fitness</a></li>
                <li>Instagram: <strong>#ATXRunClub  #AustinWellness  #GirlsWhoRunATX</strong></li>
            </ul>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Austin Babe Radar</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f0f13;
    color: #e8e8f0;
    min-height: 100vh;
    padding: 32px 16px 64px;
  }}
  .header {{
    text-align: center;
    margin-bottom: 40px;
  }}
  .header h1 {{
    font-size: 2.4rem;
    font-weight: 800;
    background: linear-gradient(135deg, #ff6ec4, #7873f5, #4adede);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
  }}
  .header .subtitle {{
    color: #888;
    margin-top: 6px;
    font-size: 0.9rem;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
    max-width: 1100px;
    margin: 0 auto;
  }}
  .card {{
    display: block;
    background: #1a1a24;
    border: 1px solid #2a2a38;
    border-radius: 14px;
    padding: 18px 20px;
    text-decoration: none;
    color: inherit;
    transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
  }}
  .card:hover {{
    transform: translateY(-3px);
    border-color: #7873f5;
    box-shadow: 0 8px 32px rgba(120,115,245,0.15);
  }}
  .card-top {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }}
  .badge {{
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 99px;
  }}
  .date {{
    font-size: 0.8rem;
    color: #888;
  }}
  .card-title {{
    font-size: 1.05rem;
    font-weight: 600;
    line-height: 1.4;
    margin-bottom: 6px;
    color: #f0f0ff;
  }}
  .card-location {{
    font-size: 0.8rem;
    color: #aaa;
    margin-bottom: 8px;
  }}
  .card-desc {{
    font-size: 0.82rem;
    color: #888;
    line-height: 1.5;
  }}
  .empty {{
    text-align: center;
    color: #666;
    padding: 60px 20px;
    grid-column: 1 / -1;
    font-size: 1rem;
    line-height: 1.8;
  }}
  .manual {{
    max-width: 1100px;
    margin: 48px auto 0;
    background: #1a1a24;
    border: 1px solid #2a2a38;
    border-radius: 14px;
    padding: 24px 28px;
  }}
  .manual h3 {{
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #888;
    margin-bottom: 14px;
  }}
  .manual ul {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .manual a {{
    color: #7873f5;
    text-decoration: none;
    font-size: 0.9rem;
  }}
  .manual a:hover {{ text-decoration: underline; }}
  .manual strong {{ color: #e8e8f0; }}
  .count {{
    text-align: center;
    color: #666;
    font-size: 0.82rem;
    margin-bottom: 20px;
  }}
</style>
</head>
<body>
<div class="header">
  <h1>Austin Babe Radar</h1>
  <div class="subtitle">Early-signal women's events in ATX &nbsp;·&nbsp; {date_str}</div>
</div>
<div class="count">{len(events[:TOP_N])} events found</div>
<div class="grid">
{cards_html}
</div>
{manual}
</body>
</html>"""


def open_in_browser(events: list[dict]) -> str:
    html = build_html(events)
    # Write to a temp file that persists (don't use delete=True — browser needs to read it)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        prefix="austin_radar_",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file://{tmp.name}")
    print(f"[BROWSER] Opened results → {tmp.name}")
    return tmp.name


# ===========================================================================
# EXPORT: CSV
# ===========================================================================

def save_to_csv(events: list[dict]) -> str:
    filename   = f"austin_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["source", "date", "name", "location", "text", "url"]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events[:TOP_N])

    print(f"[SAVED]   {filename}  ({min(TOP_N, len(events))} rows)")
    return filename


# ===========================================================================
# EXPORT: email (HTML)
# ===========================================================================

def email_results(events: list[dict]) -> None:
    if not EMAIL_TO:
        print("[EMAIL] No recipients configured.")
        print("  Set env vars: EMAIL_TO and EMAIL_TO_FRIEND")
        print("  Or edit the EMAIL_TO list at the top of babe_radar.py")
        return

    if not events:
        print("[EMAIL] Nothing to send.")
        return

    html_body = build_html(events)

    # Plain-text fallback
    lines = [f"Austin Babe Radar — {datetime.now().strftime('%Y-%m-%d')}\n"]
    for i, e in enumerate(events[:TOP_N], start=1):
        lines.append(f"#{i} [{e.get('source','')}] {e.get('date','')} — {e.get('name','')}")
        lines.append(f"   {e.get('url','')}\n")
    plain_body = "\n".join(lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Austin Babe Radar — {datetime.now().strftime('%B %d, %Y')}"
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        print(f"[EMAIL]   Sent to: {', '.join(EMAIL_TO)}")
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL ERROR] Auth failed — use a Gmail App Password, not your real password.")
        print("              myaccount.google.com/apppasswords")
    except Exception as ex:
        print(f"[EMAIL ERROR] {ex}")


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Austin Babe Radar — free scraper for early-signal ATX women's events"
    )
    parser.add_argument("--save",       action="store_true", help="Save results to CSV")
    parser.add_argument("--email",      action="store_true", help="Email HTML results")
    parser.add_argument("--no-browser", action="store_true", help="Skip opening browser")
    args = parser.parse_args()

    print("Austin Babe Radar — scraping live sources...\n")

    print("Scraping Eventbrite...")
    eb_events = scrape_eventbrite()

    print("Scraping Meetup...")
    mu_events = scrape_meetup()

    all_events = aggregate([eb_events, mu_events])

    print(f"\nTotal: {len(all_events)} events aggregated\n")

    if not args.no_browser:
        open_in_browser(all_events)

    if args.save:
        save_to_csv(all_events)

    if args.email:
        email_results(all_events)

    if not all_events:
        print("No events found — these sites may be JS-rendered.")
        print("Try the manual links that opened in your browser.\n")


if __name__ == "__main__":
    main()
