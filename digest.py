import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from jobspy import scrape_jobs

load_dotenv()

logger = logging.getLogger("job_digest")
POSTED_JOBS_FILE = Path(os.getenv("POSTED_JOBS_FILE", "posted_jobs.json"))
DISCORD_API = "https://discord.com/api/v10"

blacklist_companies = {
    "Team Remotely Inc",
    "HireMeFast LLC",
    "Get It Recruit - Information Technology",
    "Offered.ai",
    "4 Staffing Corp",
    "myGwork - LGBTQ+ Business Community",
    "Patterned Learning AI",
    "Mindpal",
    "Phoenix Recruiting",
    "SkyRecruitment",
    "Phoenix Recruitment",
    "Patterned Learning Career",
    "SysMind",
    "SysMind LLC",
    "Motion Recruitment",
}

bad_roles = {
    "unpaid",
    "senior",
    "lead",
    "manager",
    "director",
    "principal",
    "vp",
    "sr.",
    "sr",
    "senior",
    "lead",
    "manager",
    "director",
    "principal",
    "vp",
    "snr",
    "ii",
    "iii",
}


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _parse_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _parse_list(name: str, fallback_name: str, default: str) -> list[str]:
    raw = _env(name, "") or _env(fallback_name, default)
    separator = "|" if "|" in raw else ","
    return [item.strip() for item in raw.split(separator) if item.strip()]


def _config() -> dict:
    channel_id = _env("JOBS_CHANNEL_ID", "") or _env("FT_CHANNEL_ID", "")
    if not channel_id:
        raise ValueError("Set JOBS_CHANNEL_ID in environment or GitHub secrets.")
    token = _env("TOKEN", "") or _env("DISCORD_TOKEN", "")
    if not token:
        raise ValueError("Set TOKEN (or DISCORD_TOKEN) in environment or GitHub secrets.")

    search_terms = _parse_list(
        "SEARCH_TERMS",
        "SEARCH_TERM",
        "software engineer",
    )
    search_locations = _parse_list(
        "SEARCH_LOCATIONS",
        "SEARCH_LOCATION",
        "India",
    )
    title_keywords = _parse_list(
        "TITLE_KEYWORDS",
        "TITLE_KEYWORDS",
        "|".join(search_terms),
    )

    return {
        "token": token,
        "channel_id": channel_id,
        "search_terms": search_terms,
        "search_locations": search_locations,
        "title_keywords": [kw.lower() for kw in title_keywords],
        "results_wanted": _parse_int("RESULTS_WANTED", 50),
        "hours_old": _parse_int("HOURS_OLD", 6),
    }


def _load_posted_ids() -> set[str]:
    if not POSTED_JOBS_FILE.exists():
        return set()
    try:
        data = json.loads(POSTED_JOBS_FILE.read_text(encoding="utf-8"))
        return set(data.get("job_ids", []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", POSTED_JOBS_FILE, exc)
        return set()


def _save_posted_ids(job_ids: set[str], max_ids: int = 5000) -> None:
    trimmed = list(job_ids)[-max_ids:]
    POSTED_JOBS_FILE.write_text(
        json.dumps({"job_ids": trimmed}, indent=2),
        encoding="utf-8",
    )


def _hours_ago_label(row) -> str:
    if "date_posted" in row.index and row["date_posted"] is not None and str(row["date_posted"]) not in ("", "NaT"):
        posted = row["date_posted"]
        if hasattr(posted, "tzinfo") and posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        elif not hasattr(posted, "tzinfo"):
            return str(posted)
        delta = datetime.now(timezone.utc) - posted.astimezone(timezone.utc)
        hours = max(int(delta.total_seconds() // 3600), 0)
        if hours < 1:
            return "<1 hr ago"
        if hours == 1:
            return "1 hr ago"
        if hours < 24:
            return f"{hours} hrs ago"
        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''} ago"
    return "recently"


def _job_embed(row, hours_label: str) -> dict:
    title = str(row.get("title", "Unknown role"))[:256]
    company = str(row.get("company", "Unknown company"))[:256]
    job_url = str(row.get("job_url", ""))
    job_id = str(row.get("id", "N/A"))[:256]

    embed = {
        "title": title,
        "color": 0x5865F2,
        "fields": [
            {"name": "Company", "value": company, "inline": True},
            {"name": "Job ID", "value": job_id, "inline": True},
            {"name": "Posted", "value": hours_label, "inline": True},
        ],
    }
    if job_url:
        embed["url"] = job_url
        embed["fields"].append({"name": "Apply", "value": f"[Open listing]({job_url})", "inline": False})
    return embed


def _should_skip(row, title_keywords: list[str]) -> bool:
    company = row.get("company", "")
    title = str(row.get("title", "")).lower()
    if company in blacklist_companies:
        return True
    if any(term in title for term in bad_roles):
        return True
    if title_keywords and not any(keyword in title for keyword in title_keywords):
        return True
    return False


def _discord_headers(token: str) -> dict:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def _send_message(token: str, channel_id: str, payload: dict) -> None:
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    response = requests.post(url, headers=_discord_headers(token), json=payload, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Discord API error {response.status_code}: {response.text}")


def scrape_jobs_for_digest(cfg: dict) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    query_count = len(cfg["search_terms"]) * len(cfg["search_locations"])
    per_query = max(5, cfg["results_wanted"] // max(query_count, 1))

    for term in cfg["search_terms"]:
        for location in cfg["search_locations"]:
            logger.info("Scraping '%s' in '%s'...", term, location)
            batch = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=location,
                results_wanted=per_query,
                hours_old=cfg["hours_old"],
            )
            if not batch.empty:
                frames.append(batch)
            time.sleep(0.5)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "id" in combined.columns:
        combined = combined.drop_duplicates(subset=["id"])
    return combined


def run_digest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = _config()
    posted_ids = _load_posted_ids()
    new_ids = set(posted_ids)

    logger.info(
        "Scraping %s terms across %s locations...",
        len(cfg["search_terms"]),
        len(cfg["search_locations"]),
    )
    jobs = scrape_jobs_for_digest(cfg)

    if jobs.empty:
        logger.info("Scrape returned zero jobs — nothing to post.")
        return 0

    pending: list[tuple[str, dict]] = []

    for _, row in jobs.iterrows():
        if len(pending) >= cfg["results_wanted"]:
            break
        if _should_skip(row, cfg["title_keywords"]):
            continue

        job_id = str(row.get("id", ""))
        if not job_id or job_id in posted_ids:
            continue

        pending.append((job_id, _job_embed(row, _hours_ago_label(row))))

    if not pending:
        logger.info("No new jobs this run — all listings were already posted.")
        return 0

    locations_label = ", ".join(cfg["search_locations"])
    header = {
        "embeds": [
            {
                "title": "New job listings",
                "description": (
                    f"**{len(pending)}** new listing{'s' if len(pending) != 1 else ''} from LinkedIn "
                    f"({locations_label} · last {cfg['hours_old']}h)"
                ),
                "color": 0x57F287,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Tap a role title or Apply link to open the listing"},
            }
        ]
    }
    _send_message(cfg["token"], cfg["channel_id"], header)

    batch: list[dict] = []
    for job_id, embed in pending:
        new_ids.add(job_id)
        batch.append(embed)

        if len(batch) == 10:
            _send_message(cfg["token"], cfg["channel_id"], {"embeds": batch})
            batch = []
            time.sleep(1.2)

    if batch:
        _send_message(cfg["token"], cfg["channel_id"], {"embeds": batch})

    _save_posted_ids(new_ids)

    summary = {
        "embeds": [
            {
                "description": f"Posted **{len(pending)}** new job{'s' if len(pending) != 1 else ''}.",
                "color": 0x57F287,
            }
        ]
    }
    _send_message(cfg["token"], cfg["channel_id"], summary)
    logger.info("Digest finished — posted %s new jobs.", len(pending))
    return len(pending)
