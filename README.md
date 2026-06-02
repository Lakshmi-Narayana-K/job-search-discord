# Job Fetcher — Discord Job Digest

Scrapes jobs from **multiple job boards** plus **LinkedIn hiring posts**, and posts new listings to your Discord channel **once daily at 7 PM IST** via **GitHub Actions**.

## Sources

### Job boards (via [JobSpy](https://github.com/speedyapply/JobSpy))

| Site | India support | Notes |
|---|---|---|
| LinkedIn | Yes | Most reliable |
| Indeed | Yes | Very reliable for India |
| Naukri | Yes | May hit captcha from cloud IPs |
| Glassdoor | Partial | Location-sensitive |
| Google Jobs | Yes | Aggregates many sites |
| ZipRecruiter | Limited | Mostly US/Canada |
| Bayt | Partial | Middle East focus |

**BDJobs** is intentionally excluded — broken in the current JobSpy release.

### LinkedIn hiring posts

Recruiters often post roles on LinkedIn with direct company/careers links. The bot discovers these via public web search (`site:linkedin.com/posts` / `pulse`) — **no LinkedIn login required**.

This is not the same as your personal LinkedIn feed (that requires login). It finds **public** hiring posts indexed on the web.

## How it works

```
Every day at 7 PM IST → GitHub Actions runs
       ↓
Scrape all job boards (LinkedIn, Indeed, Naukri, …)
       ↓
Search for public LinkedIn hiring posts
       ↓
Filter by your role keywords + dedupe
       ↓
Post new jobs to Discord
```

**No duplicates:** each listing is tracked by `site:job_id` in `posted_jobs.json`.

## Schedule (IST)

Runs **once daily at 7:00 PM IST** (`13:30 UTC`).

| Setting | Value |
|---|---|
| Cron | `30 13 * * *` |
| IST time | **7:00 PM** every day |
| Scrape window | Last **24 hours** (`HOURS_OLD=24`) |

GitHub may delay the run by a few minutes on the free tier — seeing **7:05–7:30 PM** is normal.

You can still trigger manually anytime: **Actions → Job Digest → Run workflow**.

## Setup

See previous sections for Discord bot + GitHub secrets (`TOKEN`, `JOBS_CHANNEL_ID`).

### GitHub Variables (optional)

| Variable | Default |
|---|---|
| `SEARCH_TERMS` | Your role list |
| `SEARCH_LOCATIONS` | Hyderabad, Bangalore, India |
| `TITLE_KEYWORDS` | Role filter |
| `JOB_SITES` | `linkedin\|indeed\|naukri\|glassdoor\|google\|zip_recruiter\|bayt` |
| `COUNTRY_INDEED` | `India` |
| `SCRAPE_LINKEDIN_POSTS` | `true` |
| `LINKEDIN_POSTS_MAX` | `15` |
| `RESULTS_WANTED` | `50` |
| `HOURS_OLD` | `24` |

## What gets posted

**One clean Discord message** per run — not dozens of separate posts.

```
📋 New Job Digest
   12 new roles · Hyderabad, Bangalore · last 6h

💼 LinkedIn · 5 listings
   01. Software Engineer — Amazon
       └ Apply link · 2 hrs ago

🔎 Indeed · 4 listings
   06. Full Stack Developer — Flipkart
       └ Apply link · 4 hrs ago
```

Each job title is clickable. Jobs are grouped by source with numbered entries.

## Local test

```powershell
pip install -r requirements.txt
python post_jobs.py
```

## Honest expectations

- **No sign-in** anywhere — only public data
- **Not every site works every run** — Naukri/Glassdoor may block GitHub's cloud servers; LinkedIn + Indeed are the most reliable
- **LinkedIn posts** depend on web search indexing — good coverage but not exhaustive
- **You still apply manually** — the bot is a notification layer

## Quick Shoutout

This repo uses [JobSpy](https://github.com/Bunsly/JobSpy), made possible by [@cullenwatson](https://github.com/cullenwatson) and [Bunsly](https://github.com/Bunsly).
