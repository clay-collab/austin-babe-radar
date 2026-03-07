# Austin Babe Radar

Scrapes Eventbrite and Meetup daily for early-signal trendy Austin events that attract
hot single women — wellness pop-ups, run clubs, yoga, sound baths, brunches, singles
mixers — *before* they get overrun.

**Live site:** `https://YOUR_USERNAME.github.io/austin-babe-radar`
(replace YOUR_USERNAME after you push to GitHub)

---

## Deploy to the internet (GitHub Actions + Pages)

### 1. Create a GitHub repo

Go to [github.com/new](https://github.com/new), create a repo called `austin-babe-radar`, leave it public.

### 2. Push this code

```bash
cd ~/Desktop/austin-babe-radar
git remote add origin https://github.com/YOUR_USERNAME/austin-babe-radar.git
git push -u origin main
```

### 3. Enable GitHub Pages

1. Go to your repo on GitHub → **Settings** → **Pages**
2. Under **Source**, select **Deploy from a branch**
3. Branch: `main` / Folder: `/docs`
4. Click **Save**

Your site will be live at `https://YOUR_USERNAME.github.io/austin-babe-radar` within ~1 minute.

### 4. That's it

The workflow in `.github/workflows/daily.yml` runs every day at 9am CDT.
It scrapes Eventbrite + Meetup, writes a fresh `docs/index.html`, and pushes it.
Your site auto-updates daily with no action needed.

To trigger a manual refresh anytime: GitHub → **Actions** → **Daily Radar** → **Run workflow**.

---

## Run locally

```bash
pip3 install -r requirements.txt

python3 babe_radar.py              # scrape + open results in browser
python3 babe_radar.py --save       # also export CSV
python3 babe_radar.py --email      # also email to recipients
python3 babe_radar.py --no-browser # headless / no browser popup
```

---

## Email setup (optional)

```bash
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="your_gmail_app_password"   # myaccount.google.com/apppasswords
export EMAIL_TO="you@gmail.com"
export EMAIL_TO_FRIEND="friend@gmail.com"
```

Then run:
```bash
python3 babe_radar.py --email
```

---

## Tuning

| Setting | Default | What it does |
|---|---|---|
| `TOP_N` | `20` | Max events to display |
| `SIGNAL_KEYWORDS` | (see script) | Add/remove keywords that flag relevant events |

---

## Sources

- **Eventbrite** — `/d/tx--austin/wellness/`, `/fitness/`, `/yoga/` sorted by date
- **Meetup** — women + wellness / yoga / run club searches near Austin, TX
