# Job Fetcher — Discord Hourly Digest

Scrapes LinkedIn jobs and posts **new** listings to your Discord channel **every hour**, running entirely in the cloud via **GitHub Actions**. No laptop, no terminal, no always-on bot.

## How it works

```
GitHub Actions (every hour)
        ↓
  post_jobs.py runs ~2 min
        ↓
  Scrapes recent LinkedIn jobs
        ↓
  Skips anything already posted before
        ↓
  Posts only new jobs to Discord (or stays silent if none)
        ↓
  Shuts down
```

Your phone/laptop Discord apps receive the posts like any normal message. Tap the role title or **Apply** link to open the listing.

**No duplicates:** every job ID is saved in `posted_jobs.json` (cached between runs). The same listing will never be posted twice.

## One-time setup

### 1. Discord bot

1. Create a server (or use an existing one).
2. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
3. Under **Installation**, enable **Guild Install**, add the bot scope, grant **Send Messages** + **Embed Links**.
4. Install the bot into your server using the generated link.
5. **Bot** tab → **Reset Token** → copy the token (you'll add this as a GitHub secret).
6. Right-click your target channel → **Copy Channel ID** (enable Developer Mode under User Settings → Advanced if needed).

### 2. Push to GitHub

Push this repo to GitHub (public repo = unlimited free Actions minutes).

### 3. Add GitHub secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `TOKEN` | Your Discord bot token |
| `JOBS_CHANNEL_ID` | Your Discord channel ID |

### 4. Optional variables

**Settings → Secrets and variables → Actions → Variables** (defaults are fine if you skip these):

| Variable | Default | Purpose |
|---|---|---|
| `SEARCH_TERMS` | `Software Engineer\|Software Developer\|...` | Pipe-separated LinkedIn search queries |
| `SEARCH_LOCATIONS` | `Hyderabad, India\|Bangalore, India\|India` | Pipe-separated locations |
| `TITLE_KEYWORDS` | (same as search terms) | Only post jobs whose title matches one of these |
| `RESULTS_WANTED` | `50` | Max new jobs per run |
| `HOURS_OLD` | `2` | Only scrape listings from the last N hours |

### 5. Test it

Go to **Actions → Hourly Job Digest → Run workflow**. Jobs should appear in Discord within a couple of minutes.

After that, it runs automatically **every hour**.

## What gets posted

Each job is a compact embed:

- **Role title** (clickable → job URL)
- **Company name**
- **Job ID**
- **Posted** (e.g. `3 hrs ago`)
- **Apply** link

If an hourly run finds no new jobs, **nothing is posted** to Discord (no spam).

## Local testing (optional)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# fill in TOKEN and JOBS_CHANNEL_ID
python post_jobs.py
```

## Changing the schedule

Edit `.github/workflows/hourly-jobs.yml`:

```yaml
schedule:
  - cron: "0 * * * *"   # every hour at :00 UTC
```

Use [crontab.guru](https://crontab.guru) to customize. GitHub cron always uses **UTC**.

## Cost

- **Public repo**: free (~2 min × 24 runs ≈ 48 min/day).
- **Private repo**: 2,000 free minutes/month — hourly uses ~1,440 min/month.

## Quick Shoutout

This repo uses [JobSpy](https://github.com/Bunsly/JobSpy), a jobs scraper library for LinkedIn, Indeed, Glassdoor, Google & ZipRecruiter, made possible by [@cullenwatson](https://github.com/cullenwatson) and the talented engineers at [Bunsly](https://github.com/Bunsly).
