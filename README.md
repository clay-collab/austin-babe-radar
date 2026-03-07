# Austin Babe Radar

Scans X (Twitter) for **early-signal posts** about trendy Austin events that attract
hot single women — wellness pop-ups, run clubs, yoga, sound baths, brunches, singles
mixers — *before* they get overrun.

The trick: filter for **low-engagement posts** (< 100 likes). If a fitness studio just
announced a Saturday pop-up and it has 3 likes, you found it first.

---

## Quickstart

### 1. Get a Bearer Token

1. Go to [developer.twitter.com](https://developer.twitter.com)
2. Create a project + app (Free tier is enough for recent search)
3. Copy the **Bearer Token** from your app's *Keys & Tokens* tab

### 2. Install dependency

```bash
pip install requests
```

### 3. Set your token

Option A — environment variable (recommended):
```bash
export X_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAYour..."
```

Option B — edit `babe_radar.py` directly:
```python
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAYour..."
```

### 4. Run it

```bash
# Print results to terminal
python babe_radar.py

# Save top 10 to CSV
python babe_radar.py --save

# Email results
python babe_radar.py --email

# Both
python babe_radar.py --save --email
```

---

## Email Setup (optional)

Edit the SMTP block at the top of `babe_radar.py`, or set env vars:

```bash
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="your_gmail_app_password"   # App Password, not your real password
export EMAIL_TO="you@gmail.com"
```

For Gmail App Passwords: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

---

## Tuning the Radar

| Setting | Default | What it does |
|---|---|---|
| `MAX_LIKES_THRESHOLD` | `100` | Posts with fewer likes than this are "early signal" |
| `MAX_RESULTS` | `25` | How many X posts to fetch per run |
| `TOP_N` | `10` | How many results to show / export |
| `SINCE_DATE` | `2026-03-01` | Only posts after this date |
| `QUERY` | (see script) | Add / remove keywords to tune signal |

---

## Future Sources (TODOs in code)

- `scrape_sweatpals()` — scrape Sweatpals.com for Austin women's fitness events
- `scrape_eventbrite()` — scrape Eventbrite newly-listed Austin wellness events
- Both are stubbed with BeautifulSoup instructions — uncomment when ready

---

## Manual Leads (printed every run)

- **Sweatpals.com** — Ladies-Only Austin Events
- **Eventbrite** — Search "Austin wellness", sort by Newly Listed
- **Instagram** — `#ATXRunClub` `#AustinWellness` `#GirlsWhoRunATX`
- **Meetup.com** — Fitness & Health, Austin, Women's groups
