# Job Fetcher — Discord Job Digest

Scrapes jobs from **multiple job boards** plus **LinkedIn hiring posts**, and posts new listings to your Discord channel every 6 hours via **GitHub Actions**.

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
Every 6 hours → GitHub Actions runs
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
| `HOURS_OLD` | `6` |

## What gets posted

Each embed shows:

- **Source** (LinkedIn, Naukri, LinkedIn Post, etc.)
- **Role title** (clickable)
- **Company**
- **Posted** time
- **Apply** link (direct company URL when available)

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
