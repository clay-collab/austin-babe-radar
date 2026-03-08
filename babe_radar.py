#!/usr/bin/env python3
"""
Austin Babe Radar v2
====================
Scrapes Eventbrite + Meetup for trending coed events near downtown Austin that
TikTok/IG "girlie culture" would promote — run clubs, hot pilates, sound baths,
brunch, art walks, sip & paints — before other guys find out.

Sources (free, no API key needed):
  - Eventbrite: wellness, fitness, yoga, brunch, social, art, etc.
  - Meetup: run club, yoga, wellness, social, fitness, outdoor, etc.

Usage:
    python3 babe_radar.py               # scrape + open results in browser
    python3 babe_radar.py --save        # also save to CSV
    python3 babe_radar.py --email       # also email results
    python3 babe_radar.py --no-browser  # headless, no browser popup
"""

import os
import re
import csv
import json
import math
import time
import smtplib
import argparse
import tempfile
import webbrowser
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape as html_escape
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===========================================================================
# CONFIG
# ===========================================================================

TOP_N = 25

# Downtown Austin center
DOWNTOWN_LAT = 30.2672
DOWNTOWN_LON = -97.7431
MAX_DISTANCE_MILES = 5.0

# ---------------------------------------------------------------------------
# SMTP / Email (only needed with --email)
# ---------------------------------------------------------------------------
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "your@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your_app_password")
EMAIL_TO = [
    os.getenv("EMAIL_TO",        "your@gmail.com"),
    os.getenv("EMAIL_TO_FRIEND", ""),
]
EMAIL_TO = [e for e in EMAIL_TO if e and e != "your@gmail.com"]

# ---------------------------------------------------------------------------
# Browser-like headers
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

# ---------------------------------------------------------------------------
# Keywords: coed-friendly TikTok/IG trending activities
# ---------------------------------------------------------------------------
SIGNAL_KEYWORDS = [
    # Fitness / movement
    "run club", "running club", "hot pilates", "pilates", "hot yoga",
    "sunset yoga", "yoga in the park", "barre", "reformer", "spin",
    "hiit", "sculpt", "cycle",
    # Wellness / mindfulness
    "sound bath", "sound healing", "breathwork", "meditation",
    "wellness", "cold plunge", "ice bath", "sauna",
    # Food / drink social
    "brunch", "matcha", "sip and paint", "sip & paint",
    "wine tasting", "coffee crawl", "farmers market", "food pop up",
    # Creative / cultural
    "art walk", "art market", "pop up", "pop-up", "gallery",
    "paint night", "pottery", "ceramics", "flower arrangement",
    # Outdoor / social
    "sunset", "rooftop", "paddleboard", "kayak", "hike",
    "bike ride", "social ride", "outdoor cinema", "picnic",
    # Explicitly social / mixer
    "mixer", "social", "singles", "speed dating", "young professionals",
]

# Events with these phrases are likely women-only — skip them (we want coed)
EXCLUDE_KEYWORDS = [
    # Women-only
    "girls night", "girls only", "ladies night", "ladies only",
    "women only", "women's circle", "womens circle", "woman's circle",
    "sisterhood", "sister circle", "feminine collective",
    "moms only", "mothers only", "bridal", "bachelorette",
    "women who", "for women", "for ladies", "girls who",
    "femme only", "female only",
    "woman network", "women network", "women's network",
    "for her", "she runs", "girl tribe", "lady boss",
    "mama", "moms group", "mom group",
    # Age-restricted groups (not our demo)
    "50s", "over 50", "50+", "55+", "60+", "senior", "retiree",
    "40s and 50s", "50 and over", "fit 50",
    # Too young
    "teen ", "teens", "teenager", "teenagers", "youth", "ages 13", "ages 14",
    "ages 15", "ages 16", "13-18", "high school", "middle school",
    # Age-targeted singles (e.g. "born 1965-1985")
    "born 196", "born 197", "born 198",
    # LGBTQ / Queer-focused
    "queer", "lgbtq", "lgbt", "pride", "drag", "drag brunch",
    "drag queen", "drag show", "nonbinary", "non-binary", "trans ",
    "two-spirit", "sapphic", "leather", "kink",
    "lesbian", "lesbians", "gay ",
    # Religious
    "bible study", "bible", "church", "worship service", "prayer group",
    # Woke / activist
    "decolonize", "decolonizing", "anti-racist", "antiracist",
    "abolition", "mutual aid", "reparations",
    "bipoc only", "poc only", "safe space",
    "social justice", "allyship", "intersectional",
    "privilege", "patriarchy", "dismantle",
    "join our directory", "be a resource",
    "inclusion workshop", "diversity workshop", "dei ",
    "anti-oppression", "healing justice",
    # Racial / ethnic identity-focused (not general audience)
    "black wellness", "for black", "melanin", "african american wellness",
    "asian wellness", "for asian", "asian american", "aapi ",
    "hispanic wellness", "for hispanic", "for latino", "for latina", "latinx",
    "indigenous wellness", "for indigenous", "native american wellness",
    "jewish wellness", "for jewish",
    "arab american",
    "people of color", "communities of color", "minority community",
    # Professional / work-related (not fun)
    "advertising mastery", "social media advertising", "digital marketing",
    "job fair", "career fair", "resume", "linkedin",
    "business workshop", "sales training",
    "b2b", "lead generation", "networking for business",
    "professional development", "career development", "career coaching",
    "pitch competition",
    "how to grow", "grow your business", "scale your", "monetize",
    "real estate investing", "passive income", "side hustle",
    "workshop for entrepreneurs", "for founders", "for executives",
    "conference",
]

# ---------------------------------------------------------------------------
# Category classification: workout vs social
# ---------------------------------------------------------------------------
WORKOUT_KEYWORDS = [
    "run club", "running club", "hot pilates", "pilates", "hot yoga",
    "yoga", "barre", "reformer", "spin", "cycle", "hiit", "sculpt",
    "crossfit", "bootcamp", "boot camp", "strength", "cardio",
    "paddleboard", "kayak", "hike", "hiking", "bike ride", "social ride",
    "cold plunge", "ice bath", "sauna", "fitness",
]

SPIRITUAL_KEYWORDS = [
    "sound bath", "sound healing", "breathwork", "meditation",
    "wellness retreat", "cacao ceremony", "kirtan", "ecstatic dance",
    "reiki", "energy healing", "crystal", "full moon", "new moon",
    "sacred", "ceremony", "mindfulness", "zen",
]

SOCIAL_KEYWORDS = [
    "brunch", "matcha", "sip and paint", "sip & paint",
    "wine tasting", "coffee crawl", "paint night", "pottery",
    "ceramics", "flower arrangement", "gallery", "art walk",
    "art market", "mixer", "social", "singles", "speed dating",
    "young professionals", "rooftop", "outdoor cinema", "picnic",
    "farmers market", "food pop up", "pop up", "pop-up",
    "sunset", "wellness",
]


# ===========================================================================
# DISTANCE: Haversine formula
# ===========================================================================

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ===========================================================================
# HELPERS
# ===========================================================================

def _is_relevant(text: str) -> bool:
    lower = text.lower()
    if any(ex in lower for ex in EXCLUDE_KEYWORDS):
        return False
    return any(kw in lower for kw in SIGNAL_KEYWORDS)


def _classify_category(text: str) -> str:
    """Classify event as 'Workout', 'Spiritual', or 'Social'."""
    lower = text.lower()
    is_workout   = any(kw in lower for kw in WORKOUT_KEYWORDS)
    is_spiritual = any(kw in lower for kw in SPIRITUAL_KEYWORDS)
    is_social    = any(kw in lower for kw in SOCIAL_KEYWORDS)
    # Priority: Spiritual > Workout > Social
    if is_spiritual and not is_workout:
        return "Spiritual"
    if is_workout:
        return "Workout"
    if is_social:
        return "Social"
    return "Social"


def _add_computed_fields(event: dict) -> dict:
    """Add distance_miles and day_of_week to an event dict."""
    # Distance
    lat = event.get("latitude")
    lon = event.get("longitude")
    if lat is not None and lon is not None:
        try:
            event["distance_miles"] = round(
                haversine_miles(DOWNTOWN_LAT, DOWNTOWN_LON, float(lat), float(lon)), 1
            )
        except (ValueError, TypeError):
            event["distance_miles"] = None
    else:
        event["distance_miles"] = None

    # Friendly date + time: "Tuesday 7pm"
    date_str = event.get("date") or ""
    time_str = event.get("time") or ""
    if len(date_str) >= 10:
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            if dt.date() == datetime.now().date():
                event["day_of_week"] = "Today"
            else:
                event["day_of_week"] = dt.strftime("%A")
        except ValueError:
            event["day_of_week"] = ""
    else:
        event["day_of_week"] = ""

    # Convert 24h time like "19:00" to "7pm"
    if time_str and ":" in time_str:
        try:
            t = datetime.strptime(time_str.strip()[:5], "%H:%M")
            if t.minute == 0:
                event["friendly_time"] = t.strftime("%-I%p").lower()
            else:
                event["friendly_time"] = t.strftime("%-I:%M%p").lower()
        except ValueError:
            event["friendly_time"] = time_str
    else:
        event["friendly_time"] = ""

    # Category
    event["category"] = _classify_category(
        (event.get("name") or "") + " " + (event.get("text") or "")
    )

    return event


def _format_price(event: dict) -> str:
    low  = event.get("price_low")
    high = event.get("price_high")
    if event.get("is_free"):
        return "FREE"
    if low is not None and high is not None:
        if low == 0 and high == 0:
            return "FREE"
        if low == 0 and high > 0:
            return f"FREE – ${high:.0f}"
        if low == high:
            return f"${low:.0f}"
        return f"${low:.0f} – ${high:.0f}"
    fee = event.get("fee")
    if fee:
        return "Paid"
    return ""


def _format_traction(event: dict) -> str:
    parts = []
    rsvp = event.get("rsvp_count")
    interested = event.get("interested_count")
    avail = event.get("availability") or ""

    if rsvp is not None and rsvp > 0:
        icon = "🔥" if rsvp >= 50 else ("⚡" if rsvp >= 20 else "👥")
        parts.append(f"{icon} {rsvp} going")
    if interested is not None and interested > 0:
        parts.append(f"👀 {interested} interested")
    if "SoldOut" in avail:
        parts.append("🚫 Sold out")
    elif "Limited" in avail:
        parts.append("⚡ Almost sold out")

    return " · ".join(parts)


# ===========================================================================
# SOURCE 1: Eventbrite (via window.__SERVER_DATA__)
# ===========================================================================

EVENTBRITE_URLS = [
    "https://www.eventbrite.com/d/tx--austin/wellness/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/fitness/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/yoga/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/brunch/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/sound-bath/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/art-walk/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/pop-up/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/social/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/run-club/?sort=date",
    "https://www.eventbrite.com/d/tx--austin/pilates/?sort=date",
]


def scrape_eventbrite() -> list[dict]:
    results   = []
    seen_urls = set()

    for url in EVENTBRITE_URLS:
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        except Exception as e:
            print(f"  [Eventbrite] Error: {e}")
            continue
        if resp.status_code != 200:
            print(f"  [Eventbrite] HTTP {resp.status_code} — {url.split('/')[-2]}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # --- Strategy A: window.__SERVER_DATA__ ---
        for script in soup.find_all("script"):
            raw = script.string or ""
            if "window.__SERVER_DATA__" not in raw:
                continue
            try:
                eq_idx = raw.index("window.__SERVER_DATA__")
                eq_idx = raw.index("=", eq_idx) + 1
                json_str = raw[eq_idx:].strip()
                server_data, _ = json.JSONDecoder().raw_decode(json_str)
            except (ValueError, json.JSONDecodeError):
                continue

            events_list = (
                server_data
                .get("search_data", {})
                .get("events", {})
                .get("results", [])
            )

            for ev in events_list:
                event_url = ev.get("url", "")
                if not event_url or event_url in seen_urls:
                    continue

                name    = ev.get("name") or ""
                summary = ev.get("summary") or ""
                if not _is_relevant(name + " " + summary):
                    continue

                seen_urls.add(event_url)

                pv   = ev.get("primary_venue") or {}
                addr = pv.get("address") or {}
                lat  = None
                lon  = None
                try:
                    lat = float(addr.get("latitude", ""))
                    lon = float(addr.get("longitude", ""))
                except (ValueError, TypeError):
                    pass

                results.append({
                    "source":           "Eventbrite",
                    "date":             ev.get("start_date", ""),
                    "time":             ev.get("start_time", ""),
                    "name":             name,
                    "text":             summary[:300] if summary else name,
                    "url":              event_url,
                    "venue_name":       pv.get("name", ""),
                    "address":          addr.get("localized_address_display", ""),
                    "latitude":         lat,
                    "longitude":        lon,
                    "price_low":        None,
                    "price_high":       None,
                    "is_free":          None,
                    "availability":     "",
                    "rsvp_count":       None,
                    "interested_count": None,
                    "fee":              None,
                })

        # --- Strategy B: JSON-LD fallback ---
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") != "Event":
                        continue
                    event_url = item.get("url", "")
                    if not event_url or event_url in seen_urls:
                        continue
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    if not _is_relevant(name + " " + desc):
                        continue
                    seen_urls.add(event_url)

                    loc  = item.get("location") or {}
                    addr = loc.get("address") or {} if isinstance(loc, dict) else {}

                    results.append({
                        "source":           "Eventbrite",
                        "date":             (item.get("startDate") or "")[:10],
                        "time":             "",
                        "name":             name,
                        "text":             desc[:300] if desc else name,
                        "url":              event_url,
                        "venue_name":       loc.get("name", "") if isinstance(loc, dict) else "",
                        "address":          addr.get("streetAddress", ""),
                        "latitude":         None,
                        "longitude":        None,
                        "price_low":        None,
                        "price_high":       None,
                        "is_free":          None,
                        "availability":     "",
                        "rsvp_count":       None,
                        "interested_count": None,
                        "fee":              None,
                    })
            except (json.JSONDecodeError, AttributeError):
                continue

        time.sleep(0.5)  # be polite between search pages

    print(f"  [Eventbrite] {len(results)} relevant events")
    return results


def fetch_eventbrite_prices(events: list[dict], max_fetch: int = 20) -> list[dict]:
    """Second pass: fetch individual Eventbrite pages to get price from JSON-LD offers."""
    eb_events = [e for e in events if e.get("source") == "Eventbrite"][:max_fetch]
    if not eb_events:
        return events

    print(f"  [Eventbrite] Fetching prices for {len(eb_events)} events...")
    for e in eb_events:
        try:
            resp = requests.get(e["url"], headers=BROWSER_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for script in soup.find_all("script", type="application/ld+json"):
                data = json.loads(script.string or "")
                if not isinstance(data, dict) or data.get("@type") != "Event":
                    continue
                offers = data.get("offers", [])
                if not offers:
                    continue
                offer = offers[0] if isinstance(offers, list) else offers
                low  = float(offer.get("lowPrice", 0))
                high = float(offer.get("highPrice", 0))
                e["price_low"]    = low
                e["price_high"]   = high
                e["is_free"]      = (low == 0 and high == 0)
                e["availability"] = offer.get("availability", "")
                break
        except Exception:
            pass
        time.sleep(0.3)

    return events


# ===========================================================================
# SOURCE 2: Meetup (fixed Austin URLs + traction from __NEXT_DATA__)
# ===========================================================================

MEETUP_URLS = [
    "https://www.meetup.com/find/?keywords=run+club&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=yoga&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=pilates&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=sound+bath&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=wellness&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=social&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=fitness&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=outdoor&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=art&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
    "https://www.meetup.com/find/?keywords=brunch&location=us--tx--Austin&source=EVENTS&eventType=inPerson",
]


def scrape_meetup() -> list[dict]:
    results   = []
    seen_urls = set()

    for url in MEETUP_URLS:
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        except Exception as e:
            print(f"  [Meetup] Error: {e}")
            continue
        if resp.status_code != 200:
            print(f"  [Meetup] HTTP {resp.status_code}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # --- Strategy A: __NEXT_DATA__ (richer: has RSVP counts, venue) ---
        next_tag = soup.find("script", id="__NEXT_DATA__")
        if next_tag:
            try:
                nd = json.loads(next_tag.string or "")
                # Build group name lookup from Apollo cache refs
                group_names = _build_group_lookup(nd)
                _walk_meetup_data(nd, results, seen_urls, group_names=group_names)
            except (json.JSONDecodeError, AttributeError):
                pass

        # --- Strategy B: JSON-LD fallback ---
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") != "Event":
                        continue
                    event_url = item.get("url", "")
                    if not event_url or event_url in seen_urls:
                        continue
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    organizer = (item.get("organizer") or {}).get("name", "")
                    full_text = f"{name} {desc} {organizer} {event_url}"
                    if not _is_relevant(full_text):
                        continue
                    seen_urls.add(event_url)

                    loc = item.get("location") or {}
                    loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                    loc_addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                    city = loc_addr.get("addressLocality", "") if isinstance(loc_addr, dict) else ""

                    results.append({
                        "source":           "Meetup",
                        "date":             (item.get("startDate") or "")[:10],
                        "time":             (item.get("startDate") or "")[11:16],
                        "name":             name,
                        "text":             desc[:300] if desc else name,
                        "url":              event_url,
                        "venue_name":       loc_name,
                        "address":          city,
                        "latitude":         None,
                        "longitude":        None,
                        "price_low":        None,
                        "price_high":       None,
                        "is_free":          None,
                        "availability":     "",
                        "rsvp_count":       None,
                        "interested_count": None,
                        "fee":              None,
                    })
            except (json.JSONDecodeError, AttributeError):
                continue

        time.sleep(0.5)

    print(f"  [Meetup]     {len(results)} relevant events")
    return results


def _build_group_lookup(obj, result: dict = None, depth: int = 0) -> dict:
    """Walk __NEXT_DATA__ to find Group objects and map their __ref/id to name."""
    if result is None:
        result = {}
    if depth > 15:
        return result
    if isinstance(obj, dict):
        if obj.get("__typename") == "Group" and obj.get("name"):
            ref = obj.get("__ref") or f"Group:{obj.get('id', '')}"
            result[ref] = obj["name"]
            # Also map urlname for URL-based lookup
            if obj.get("urlname"):
                result[obj["urlname"]] = obj["name"]
        for v in obj.values():
            _build_group_lookup(v, result, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _build_group_lookup(item, result, depth + 1)
    return result


def _walk_meetup_data(obj, results: list, seen_urls: set, depth: int = 0,
                      group_names: dict = None) -> None:
    if group_names is None:
        group_names = {}
    if depth > 12:
        return
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("name", "")
        url   = obj.get("eventUrl") or obj.get("link") or obj.get("url", "")
        date  = (obj.get("dateTime") or obj.get("startDate") or obj.get("date") or "")

        if title and url and url not in seen_urls:
            desc = obj.get("description") or title

            # Resolve group name from Apollo cache refs
            group = obj.get("group") or {}
            group_name = ""
            if isinstance(group, dict):
                group_name = group.get("name", "")
                if not group_name:
                    ref = group.get("__ref", "")
                    group_name = group_names.get(ref, "")
                if not group_name:
                    urlname = group.get("urlname", "")
                    group_name = group_names.get(urlname, "")

            # Also use URL slug (e.g. /women-outdoors-austin/)
            url_slug = url.split("/")[3] if url.count("/") >= 4 else ""

            full_text = f"{title} {desc} {group_name} {url_slug}"
            if _is_relevant(full_text):
                seen_urls.add(url)

                # Traction
                rsvp_count = None
                interested = None
                rsvps_obj  = obj.get("rsvps")
                if isinstance(rsvps_obj, dict):
                    rsvp_count = rsvps_obj.get("totalCount")
                spi = obj.get("socialProofInsights")
                if isinstance(spi, dict):
                    interested = spi.get("totalInterestedUsers")

                # Venue
                venue = obj.get("venue") or {}
                venue_name = venue.get("name", "") if isinstance(venue, dict) else ""
                venue_addr = venue.get("address", "") if isinstance(venue, dict) else ""
                venue_city = venue.get("city", "") if isinstance(venue, dict) else ""

                # Fee
                fee = obj.get("feeSettings")

                results.append({
                    "source":           "Meetup",
                    "date":             date[:10] if date else "",
                    "time":             date[11:16] if len(date) > 11 else "",
                    "name":             title,
                    "text":             desc[:300],
                    "url":              url,
                    "venue_name":       venue_name,
                    "address":          f"{venue_addr}, {venue_city}".strip(", "),
                    "latitude":         None,
                    "longitude":        None,
                    "price_low":        None,
                    "price_high":       None,
                    "is_free":          fee is None,
                    "availability":     "",
                    "rsvp_count":       rsvp_count,
                    "interested_count": interested,
                    "fee":              fee,
                })

        for v in obj.values():
            _walk_meetup_data(v, results, seen_urls, depth + 1, group_names)
    elif isinstance(obj, list):
        for item in obj:
            _walk_meetup_data(item, results, seen_urls, depth + 1, group_names)


# ===========================================================================
# AGGREGATE: merge, distance filter, sort soonest first
# ===========================================================================

def aggregate(sources: list[list[dict]]) -> list[dict]:
    combined, seen = [], set()
    for source in sources:
        for item in source:
            url = item.get("url", "")
            if url and url in seen:
                continue
            seen.add(url)
            item = _add_computed_fields(item)
            combined.append(item)

    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    filtered = []
    for e in combined:
        # Distance filter
        dist = e.get("distance_miles")
        if dist is not None and dist > MAX_DISTANCE_MILES:
            continue
        # Only next 7 days
        d = e.get("date") or ""
        if d and (d < today or d > cutoff):
            continue
        # Min 10 going (keep if unknown)
        rsvp = e.get("rsvp_count")
        if rsvp is not None and rsvp < 10:
            continue
        filtered.append(e)

    # Sort soonest first
    filtered.sort(key=lambda x: x.get("date") or "9999-99-99")
    return filtered


# ===========================================================================
# HTML OUTPUT
# ===========================================================================

def build_html(events: list[dict]) -> str:
    now_str = datetime.now(ZoneInfo("America/Chicago")).strftime("%B %d, %Y  %-I:%M %p CST")

    # Muted source badge colors
    source_badge = {
        "Eventbrite": ("#3a2a28", "#c08070"),
        "Meetup":     ("#2a2832", "#9088b0"),
    }

    # Group events by category
    tabs = [
        ("Workout",   "#22c55e", "0f130f", [e for e in events if e.get("category") == "Workout"]),
        ("Spiritual", "#c084fc", "110f15", [e for e in events if e.get("category") == "Spiritual"]),
        ("Social",    "#38bdf8", "0f1115", [e for e in events if e.get("category") == "Social"]),
    ]

    # Build cards HTML for each tab
    tab_buttons = ""
    tab_panels = ""
    for i, (tab_name, tab_color, tab_bg, tab_events) in enumerate(tabs):
        active = " active" if i == 0 else ""
        count = len(tab_events)
        tab_buttons += f'<button class="tab{active}" data-tab="{tab_name.lower()}" data-bg="#{tab_bg}" style="--tab-color:{tab_color}">{tab_name} <span class="tab-count">{count}</span></button>\n'

        display = "grid" if i == 0 else "none"
        cards = ""
        if not tab_events:
            cards = f'<div class="empty">No {tab_name.lower()} events this week.</div>'
        else:
            for e in tab_events:
                name   = html_escape(e.get("name") or "")
                source = e.get("source", "")
                url    = e.get("url") or "#"
                bg, fg = source_badge.get(source, ("#333", "#888"))

                dow  = e.get("day_of_week", "")
                ft   = e.get("friendly_time", "")
                date_display = dow
                if ft:
                    date_display += f" {ft}" if dow else ft

                venue = html_escape(e.get("venue_name") or e.get("address") or "Austin, TX")
                dist  = e.get("distance_miles")
                dist_str = f" — {dist} mi" if dist is not None else ""

                price_str = _format_price(e)
                price_class = "free" if (e.get("is_free") or price_str == "FREE") else ""
                traction_str = _format_traction(e)

                text = e.get("text") or ""
                desc = text if text.lower().strip() != name.lower().strip() else ""
                desc = html_escape(desc[:180]) + ("..." if len(desc) > 180 else "") if desc else ""

                cards += f"""
                <a class="card" href="{url}" target="_blank" rel="noopener">
                    <div class="card-top">
                        <span class="badge" style="background:{bg};color:{fg}">{source}</span>
                        <span class="date">{date_display}</span>
                    </div>
                    <div class="card-title">{name}</div>
                    <div class="card-location">📍 {venue}{dist_str}</div>
                    {"<div class='card-price " + price_class + "'>💰 " + price_str + "</div>" if price_str else ""}
                    {"<div class='card-traction'>" + traction_str + "</div>" if traction_str else ""}
                    {"<div class='card-desc'>" + desc + "</div>" if desc else ""}
                </a>"""

        tab_panels += f'<div class="tab-panel" id="panel-{tab_name.lower()}" style="display:{display}">\n<div class="grid">{cards}\n</div>\n</div>\n'

    manual = ""

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
    background: #0f130f;
    color: #e8e8f0;
    min-height: 100vh;
    padding: 32px 16px 64px;
    transition: background 0.4s ease;
  }}
  .header {{ text-align: center; margin-bottom: 24px; }}
  .header h1 {{
    font-size: 2.4rem; font-weight: 800;
    background: linear-gradient(135deg, #ff6ec4, #7873f5, #4adede);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; letter-spacing: -0.5px;
  }}
  .header .subtitle {{ color: #888; margin-top: 6px; font-size: 0.9rem; }}
  .tabs {{
    display: flex; justify-content: center; gap: 8px;
    max-width: 500px; margin: 0 auto 28px;
  }}
  .tab {{
    flex: 1; padding: 10px 16px; border: 1px solid #2a2a38;
    border-radius: 10px; background: #1a1a24; color: #888;
    font-size: 0.95rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease;
  }}
  .tab:hover {{ border-color: #444; color: #ccc; }}
  .tab.active {{
    background: var(--tab-color); color: #fff;
    border-color: var(--tab-color);
  }}
  .tab-count {{
    font-weight: 400; font-size: 0.8rem; opacity: 0.7;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px; max-width: 1100px; margin: 0 auto;
  }}
  .card {{
    display: block; background: rgba(26,26,36,0.85); border: 1px solid #2a2a38;
    border-radius: 14px; padding: 18px 20px;
    text-decoration: none; color: inherit;
    transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
  }}
  .card:hover {{
    transform: translateY(-3px); border-color: #7873f5;
    box-shadow: 0 8px 32px rgba(120,115,245,0.15);
  }}
  .card-top {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
  .badge {{
    font-size: 0.65rem; font-weight: 600; letter-spacing: 0.3px;
    text-transform: uppercase; padding: 2px 7px; border-radius: 99px;
    opacity: 0.8;
  }}
  .date {{ font-size: 0.85rem; color: #bbb; font-weight: 500; }}
  .card-title {{
    font-size: 1.05rem; font-weight: 600; line-height: 1.4;
    margin-bottom: 6px; color: #f0f0ff;
  }}
  .card-location {{ font-size: 0.8rem; color: #aaa; margin-bottom: 6px; }}
  .card-price {{
    font-size: 0.8rem; color: #4adede; font-weight: 600; margin-bottom: 4px;
  }}
  .card-price.free {{ color: #4ade80; }}
  .card-traction {{
    font-size: 0.78rem; color: #f59e0b; margin-bottom: 6px;
  }}
  .card-desc {{
    font-size: 0.82rem; color: #888; line-height: 1.5;
  }}
  .empty {{
    text-align: center; color: #666; padding: 60px 20px;
    grid-column: 1 / -1; font-size: 1rem; line-height: 1.8;
  }}
  .tab-panel {{ max-width: 1100px; margin: 0 auto; }}
</style>
</head>
<body>
<div class="header">
  <h1>Austin Babe Radar</h1>
  <div class="subtitle">{len(events)} events within {MAX_DISTANCE_MILES:.0f} miles of downtown · next 7 days only &nbsp;·&nbsp; {now_str}</div>
</div>
<div class="tabs">
{tab_buttons}
</div>
{tab_panels}
{manual}
<script>
document.querySelectorAll('.tab').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.tab').forEach(function(b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.style.display = 'none'; }});
    btn.classList.add('active');
    var panel = document.getElementById('panel-' + btn.dataset.tab);
    if (panel) panel.style.display = 'block';
    document.body.style.background = btn.dataset.bg;
  }});
}});
</script>
</body>
</html>"""


def open_in_browser(events: list[dict]) -> str:
    html = build_html(events)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", prefix="austin_radar_",
        delete=False, encoding="utf-8",
    )
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file://{tmp.name}")
    print(f"[BROWSER] Opened → {tmp.name}")
    return tmp.name


# ===========================================================================
# EXPORT: CSV
# ===========================================================================

def save_to_csv(events: list[dict]) -> str:
    filename   = f"austin_radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = [
        "source", "category", "date", "day_of_week", "time", "name", "venue_name",
        "address", "distance_miles", "price_low", "price_high", "is_free",
        "rsvp_count", "interested_count", "text", "url",
    ]
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
        print("[EMAIL] No recipients. Set EMAIL_TO and EMAIL_TO_FRIEND env vars.")
        return
    if not events:
        print("[EMAIL] Nothing to send.")
        return

    html_body = build_html(events)
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
        print("[EMAIL ERROR] Auth failed — use a Gmail App Password.")
    except Exception as ex:
        print(f"[EMAIL ERROR] {ex}")


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Austin Babe Radar — trending coed events near downtown ATX"
    )
    parser.add_argument("--save",       action="store_true", help="Save results to CSV")
    parser.add_argument("--email",      action="store_true", help="Email HTML results")
    parser.add_argument("--no-browser", action="store_true", help="Skip opening browser")
    parser.add_argument("--output",     metavar="FILE",      help="Write HTML to file")
    parser.add_argument("--no-prices",  action="store_true", help="Skip fetching Eventbrite prices (faster)")
    args = parser.parse_args()

    print("Austin Babe Radar v2 — scraping live sources...\n")

    print("Scraping Eventbrite...")
    eb_events = scrape_eventbrite()

    print("Scraping Meetup...")
    mu_events = scrape_meetup()

    all_events = aggregate([eb_events, mu_events])

    if not args.no_prices:
        all_events = fetch_eventbrite_prices(all_events)

    print(f"\n{len(all_events)} events within {MAX_DISTANCE_MILES:.0f} mi of downtown Austin\n")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(build_html(all_events))
        print(f"[OUTPUT]  {args.output}")
    elif not args.no_browser:
        open_in_browser(all_events)

    if args.save:
        save_to_csv(all_events)

    if args.email:
        email_results(all_events)

    if not all_events:
        print("No events matched. Try widening MAX_DISTANCE_MILES or check manually.\n")


if __name__ == "__main__":
    main()
