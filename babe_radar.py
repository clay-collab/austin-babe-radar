#!/usr/bin/env python3
"""
Austin Babe Radar
=================
Scans X (Twitter) for early-signal posts about trendy Austin events that attract
hot single women — wellness pop-ups, run clubs, yoga, sound baths, brunches,
singles mixers — *before* they get flooded.

Usage:
    python babe_radar.py                   # print results
    python babe_radar.py --save            # save to CSV (austin_radar_YYYYMMDD.csv)
    python babe_radar.py --email           # email results (configure SMTP below)
    python babe_radar.py --save --email    # both

Get your Bearer Token:
    1. Go to https://developer.twitter.com
    2. Create a project + app (Free tier works for recent search)
    3. Copy the "Bearer Token" from your app's Keys & Tokens tab
    4. Replace BEARER_TOKEN below (or set env var X_BEARER_TOKEN)
"""

import os
import csv
import json
import smtplib
import argparse
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===========================================================================
# CONFIG — edit these or set environment variables
# ===========================================================================

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "YOUR_BEARER_TOKEN_HERE")

# Search settings
MAX_RESULTS = 25          # X API max per call on free tier is 10; on Basic it's 100
MAX_LIKES_THRESHOLD = 100 # "Early signal" = low engagement = under this many likes
TOP_N = 10                # How many results to display / export

# Date filter — posts since this date (ISO format YYYY-MM-DD)
SINCE_DATE = "2026-03-01"

# High-signal query: Austin + female-forward / trendy event keywords
# Filters: English, has_engagement, min_faves:1, no replies
QUERY = (
    '(Austin OR ATX) '
    '(wellness OR yoga OR "sound bath" OR "run club" OR brunch OR mixer '
    'OR "girls night" OR ladies OR women OR empowerment OR pilates OR "hot pilates") '
    f'since:{SINCE_DATE} '
    'filter:has_engagement min_faves:1 -filter:replies lang:en'
)

# ---------------------------------------------------------------------------
# SMTP / Email config (only needed if using --email)
# ---------------------------------------------------------------------------
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "your@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your_app_password")
EMAIL_TO      = os.getenv("EMAIL_TO",      "your@gmail.com")

# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------
HEADERS = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "User-Agent": "AustinBabeRadar/1.0",
}


# ===========================================================================
# CORE: X API search
# ===========================================================================

def search_x_posts() -> list[dict]:
    """
    Hit the X API v2 recent-search endpoint and return a filtered,
    sorted list of post dicts.
    """
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {
        "query":        QUERY,
        "tweet.fields": "created_at,author_id,text,public_metrics",
        "expansions":   "author_id",
        "user.fields":  "username,name",
        "max_results":  MAX_RESULTS,
        "sort_order":   "recency",
    }

    print(f"  Query: {QUERY}\n")

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
    except requests.exceptions.ConnectionError:
        print("[ERROR] Network error — check your internet connection.")
        return []
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out. Try again in a moment.")
        return []

    # --- API error handling ---
    if response.status_code == 401:
        print("[ERROR] 401 Unauthorized — your Bearer Token is invalid or missing.")
        print("        Set X_BEARER_TOKEN env var or edit BEARER_TOKEN in the script.")
        return []
    if response.status_code == 403:
        print("[ERROR] 403 Forbidden — your app may not have access to search.")
        print("        Ensure your X developer app has 'Read' permissions.")
        return []
    if response.status_code == 429:
        print("[ERROR] 429 Rate limited — you've hit the X API rate limit.")
        print("        Wait 15 minutes and try again.")
        return []
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}: {response.text}")
        return []

    data = response.json()

    if "errors" in data and "data" not in data:
        print(f"[ERROR] API returned errors: {json.dumps(data['errors'], indent=2)}")
        return []

    tweets = data.get("data", [])
    if not tweets:
        print("[INFO] No tweets returned. Try broadening QUERY or changing SINCE_DATE.")
        return []

    # Build user lookup from expansions
    users: dict[str, dict] = {
        u["id"]: u
        for u in data.get("includes", {}).get("users", [])
    }

    posts = []
    for tweet in tweets:
        user    = users.get(tweet.get("author_id", ""), {})
        metrics = tweet.get("public_metrics", {})
        likes   = metrics.get("like_count", 0)
        username = user.get("username", "unknown")

        # Early-signal filter: low engagement only
        if likes >= MAX_LIKES_THRESHOLD:
            continue

        # Basic spam filter: skip posts that literally contain "babe"
        text = tweet.get("text", "")
        if "babe" in text.lower():
            continue

        posts.append({
            "date":     tweet.get("created_at", ""),
            "user":     username,
            "name":     user.get("name", username),
            "text":     text,
            "likes":    likes,
            "retweets": metrics.get("retweet_count", 0),
            "replies":  metrics.get("reply_count", 0),
            "url":      f"https://x.com/{username}/status/{tweet['id']}",
        })

    # Sort newest first
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ===========================================================================
# OUTPUT: print to terminal
# ===========================================================================

def print_events(posts: list[dict]) -> None:
    banner = f"=== Austin Babe Radar — {datetime.now().strftime('%Y-%m-%d %H:%M')} ==="
    print(f"\n{banner}\n")

    if not posts:
        print("No fresh low-engagement signals found.")
        print("Tips:")
        print("  • Broaden SINCE_DATE (e.g., 2026-02-01)")
        print("  • Raise MAX_LIKES_THRESHOLD")
        print("  • Check X manually for #ATXEvents")
        return

    print(f"Found {len(posts)} signal(s). Showing top {min(TOP_N, len(posts))}:\n")
    print("-" * 70)

    for i, p in enumerate(posts[:TOP_N], start=1):
        date_str = p["date"][:10] if p["date"] else "unknown"
        preview  = p["text"].replace("\n", " ")[:200]
        ellipsis = "..." if len(p["text"]) > 200 else ""

        print(f"#{i}  {date_str}  @{p['user']}  ❤️ {p['likes']}  🔁 {p['retweets']}")
        print(f"    {preview}{ellipsis}")
        print(f"    {p['url']}")
        print()

    print("-" * 70)


# ===========================================================================
# EXPORT: save to CSV
# ===========================================================================

def save_to_csv(posts: list[dict]) -> str:
    filename = f"austin_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["date", "user", "name", "likes", "retweets", "replies", "text", "url"]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(posts[:TOP_N])

    print(f"[SAVED] {filename}  ({min(TOP_N, len(posts))} rows)")
    return filename


# ===========================================================================
# EXPORT: email results
# ===========================================================================

def email_results(posts: list[dict]) -> None:
    if not posts:
        print("[EMAIL] Nothing to send — no results.")
        return

    # Build plain-text body
    lines = [f"Austin Babe Radar — {datetime.now().strftime('%Y-%m-%d')}\n"]
    for i, p in enumerate(posts[:TOP_N], start=1):
        lines.append(f"#{i}  {p['date'][:10]}  @{p['user']}  ❤️ {p['likes']}")
        lines.append(f"    {p['text'][:200]}")
        lines.append(f"    {p['url']}\n")

    body = "\n".join(lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Austin Babe Radar — {datetime.now().strftime('%Y-%m-%d')}"
    msg["From"]    = SMTP_USER
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        print(f"[EMAIL] Sent to {EMAIL_TO}")
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL ERROR] Authentication failed — check SMTP_USER / SMTP_PASSWORD.")
        print("              For Gmail use an App Password, not your account password.")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


# ===========================================================================
# FUTURE SOURCES (not yet implemented — add BeautifulSoup + requests)
# ===========================================================================

def scrape_sweatpals():
    """
    TODO: Scrape https://sweatpals.com for Austin women's fitness events.

    from bs4 import BeautifulSoup
    url = "https://sweatpals.com/austin"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "html.parser")
    events = soup.find_all("div", class_="event-card")   # inspect actual class names
    for e in events:
        ...
    """
    pass


def scrape_eventbrite():
    """
    TODO: Scrape Eventbrite for newly-listed Austin wellness events.

    from bs4 import BeautifulSoup
    url = "https://www.eventbrite.com/d/tx--austin/wellness/?sort=date"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("article", {"data-testid": "search-event-card-wrapper"})
    for card in cards:
        ...
    """
    pass


# ===========================================================================
# MANUAL LEADS (always printed)
# ===========================================================================

def print_manual_leads() -> None:
    print("\nQuick manual checks worth doing right now:")
    print("  • Sweatpals.com — Ladies-Only Austin Events (yoga, runs, Pilates)")
    print("  • Eventbrite     — Search 'Austin wellness', sort by 'Newly Listed'")
    print("  • Instagram      — #ATXRunClub  #AustinWellness  #GirlsWhoRunATX")
    print("  • Meetup.com     — Category: Fitness & Health, Austin, Women's groups")
    print()


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Austin Babe Radar — catch early-signal trendy women's events in ATX"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save top results to a dated CSV file",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Email results via SMTP (configure SMTP settings at top of script)",
    )
    args = parser.parse_args()

    if BEARER_TOKEN == "YOUR_BEARER_TOKEN_HERE":
        print("[WARNING] BEARER_TOKEN is not set.")
        print("  Set env var:  export X_BEARER_TOKEN='AAA...'")
        print("  Or edit BEARER_TOKEN in babe_radar.py\n")

    print("Scanning X for emerging Austin events...")
    posts = search_x_posts()

    print_events(posts)

    if args.save:
        save_to_csv(posts)

    if args.email:
        email_results(posts)

    print_manual_leads()


if __name__ == "__main__":
    main()
