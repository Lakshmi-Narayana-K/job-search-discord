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

from linkedin_posts import fetch_hiring_posts

load_dotenv()

logger = logging.getLogger("job_digest")
POSTED_JOBS_FILE = Path(os.getenv("POSTED_JOBS_FILE", "posted_jobs.json"))
DISCORD_API = "https://discord.com/api/v10"

# All JobSpy boards. BDJobs excluded — broken in current JobSpy release.
DEFAULT_JOB_SITES = [
    "linkedin",
    "indeed",
    "naukri",
    "glassdoor",
    "google",
    "zip_recruiter",
    "bayt",
]

SITE_LABELS = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "naukri": "Naukri",
    "glassdoor": "Glassdoor",
    "google": "Google Jobs",
    "zip_recruiter": "ZipRecruiter",
    "bayt": "Bayt",
    "bdjobs": "BDJobs",
    "linkedin_post": "LinkedIn Post",
}

SOURCE_EMOJI = {
    "linkedin": "💼",
    "indeed": "🔎",
    "naukri": "🇮🇳",
    "glassdoor": "🌐",
    "google": "🔍",
    "zip_recruiter": "⚡",
    "bayt": "🌍",
    "linkedin_post": "📢",
}

SOURCE_COLORS = {
    "linkedin": 0x0A66C2,
    "indeed": 0x2164F3,
    "naukri": 0x4A90E2,
    "glassdoor": 0x0CAA41,
    "google": 0x4285F4,
    "zip_recruiter": 0x6B46C1,
    "bayt": 0xE67E22,
    "linkedin_post": 0x0A66C2,
}

SITE_ORDER = [
    "linkedin",
    "naukri",
    "indeed",
    "linkedin_post",
    "google",
    "glassdoor",
    "zip_recruiter",
    "bayt",
]

MAX_EMBED_DESCRIPTION = 3900
MAX_EMBEDS_PER_MESSAGE = 10

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


def _parse_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


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
    job_sites = _parse_list("JOB_SITES", "JOB_SITES", "|".join(DEFAULT_JOB_SITES))
    job_sites = [site.lower() for site in job_sites if site.lower() != "bdjobs"]

    return {
        "token": token,
        "channel_id": channel_id,
        "search_terms": search_terms,
        "search_locations": search_locations,
        "title_keywords": [kw.lower() for kw in title_keywords],
        "job_sites": job_sites,
        "country_indeed": _env("COUNTRY_INDEED", "India"),
        "results_wanted": _parse_int("RESULTS_WANTED", 50),
        "hours_old": _parse_int("HOURS_OLD", 6),
        "scrape_linkedin_posts": _parse_bool("SCRAPE_LINKEDIN_POSTS", True),
        "linkedin_posts_max": _parse_int("LINKEDIN_POSTS_MAX", 15),
        "linkedin_fetch_description": _parse_bool("LINKEDIN_FETCH_DESCRIPTION", True),
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
    if str(row.get("site", "")) == "linkedin_post":
        return "recent post"
    return "recently"


def _site_label(row) -> str:
    site = str(row.get("site", "unknown")).lower()
    return SITE_LABELS.get(site, site.replace("_", " ").title())


def _best_url(row) -> str:
    for key in ("job_url_direct", "job_url", "company_url_direct", "company_url"):
        value = row.get(key)
        if value and str(value).startswith("http"):
            return str(value)
    return ""


def _dedup_key(row) -> str:
    site = str(row.get("site", "unknown")).lower()
    job_id = str(row.get("id", "")).strip()
    if job_id:
        return f"{site}:{job_id}"
    url = _best_url(row)
    if url:
        return f"{site}:{url}"
    return ""


def _truncate(text: str, max_len: int) -> str:
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _format_job_line(index: int, row, hours_label: str) -> str:
    title = _truncate(row.get("title", "Unknown role"), 70)
    company = _truncate(row.get("company", "—"), 36)
    url = _best_url(row)
    source = _site_label(row)
    title_md = f"[**{title}**]({url})" if url else f"**{title}**"
    return (
        f"**{index:02d}.** {title_md}\n"
        f"└ `{company}` · {source} · *{hours_label}*"
    )


def _split_blocks(blocks: list[str], max_len: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        block_len = len(block) + (2 if current else 0)
        if current and current_len + block_len > max_len:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += block_len

    if current:
        chunks.append("\n\n".join(current))
    return chunks or [""]


def _build_consolidated_message(pending: list[tuple[str, pd.Series]], cfg: dict) -> dict:
    from collections import defaultdict

    grouped: dict[str, list[pd.Series]] = defaultdict(list)
    for _, row in pending:
        site = str(row.get("site", "other")).lower()
        grouped[site].append(row)

    locations = ", ".join(cfg["search_locations"])
    count = len(pending)

    embeds: list[dict] = [
        {
            "title": "📋 New Job Digest",
            "description": (
                f"**{count}** new role{'s' if count != 1 else ''} matched your filters.\n\n"
                f"📍 **Locations:** {locations}\n"
                f"⏱️ **Window:** last {cfg['hours_old']} hours\n"
                f"👇 **Tap any bold title below to open & apply**"
            ),
            "color": 0x5865F2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ]

    job_index = 1
    site_sections: list[tuple[str, str, int]] = []

    ordered_sites = [s for s in SITE_ORDER if s in grouped]
    ordered_sites.extend(s for s in grouped if s not in SITE_ORDER)

    for site in ordered_sites:
        rows = grouped[site]
        lines = []
        for row in rows:
            lines.append(_format_job_line(job_index, row, _hours_ago_label(row)))
            job_index += 1
        site_sections.append((site, "\n\n".join(lines), len(rows)))

    remaining_slots = MAX_EMBEDS_PER_MESSAGE - 1

    if len(site_sections) <= remaining_slots:
        for site, body, row_count in site_sections:
            emoji = SOURCE_EMOJI.get(site, "📌")
            label = SITE_LABELS.get(site, site.replace("_", " ").title())
            embeds.append(
                {
                    "title": f"{emoji} {label} · {row_count} listing{'s' if row_count != 1 else ''}",
                    "description": body[:MAX_EMBED_DESCRIPTION],
                    "color": SOURCE_COLORS.get(site, 0x5865F2),
                }
            )
    else:
        combined_blocks = []
        for site, body, row_count in site_sections:
            emoji = SOURCE_EMOJI.get(site, "📌")
            label = SITE_LABELS.get(site, site.replace("_", " ").title())
            combined_blocks.append(
                f"{emoji} **{label}** · {row_count} listing{'s' if row_count != 1 else ''}\n{body}"
            )
        chunks = _split_blocks(combined_blocks, MAX_EMBED_DESCRIPTION)
        for idx, chunk in enumerate(chunks[:remaining_slots], start=1):
            embeds.append(
                {
                    "title": f"📑 Listings ({idx}/{min(len(chunks), remaining_slots)})",
                    "description": chunk,
                    "color": 0x57F287,
                }
            )

    embeds[-1]["footer"] = {"text": f"{count} jobs total · Links open the listing or hiring post"}
    return {"embeds": embeds[:MAX_EMBEDS_PER_MESSAGE]}


def _should_skip(row, title_keywords: list[str]) -> bool:
    company = row.get("company", "")
    title = str(row.get("title", "")).lower()
    if company in blacklist_companies:
        return True
    if str(row.get("site", "")) != "linkedin_post" and any(term in title for term in bad_roles):
        return True
    if title_keywords and not any(keyword in title for keyword in title_keywords):
        return True
    return False


def _discord_headers(token: str) -> dict:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def _send_message(token: str, channel_id: str, payload: dict) -> None:
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    response = requests.post(url, headers=_discord_headers(token), json=payload, timeout=30)
    if response.status_code == 404:
        raise RuntimeError(
            "Discord channel not found (404). Use the Channel ID (right-click the #channel), not the Server ID."
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Discord API error {response.status_code}: {response.text}")


def _per_site_results(cfg: dict) -> int:
    query_count = max(
        1,
        len(cfg["search_terms"]) * len(cfg["search_locations"]),
    )
    return max(3, min(8, cfg["results_wanted"] // query_count))


def _scrape_job_boards(cfg: dict) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    per_site = _per_site_results(cfg)
    sites = cfg["job_sites"]

    for term in cfg["search_terms"]:
        for location in cfg["search_locations"]:
            logger.info("Scraping %s for '%s' in '%s'...", ", ".join(sites), term, location)
            try:
                batch = scrape_jobs(
                    site_name=sites,
                    search_term=term,
                    google_search_term=f"{term} jobs {location} India",
                    location=location,
                    results_wanted=per_site,
                    hours_old=cfg["hours_old"],
                    country_indeed=cfg["country_indeed"],
                    linkedin_fetch_description=cfg["linkedin_fetch_description"],
                    verbose=0,
                )
                if not batch.empty:
                    frames.append(batch)
            except Exception as exc:
                logger.warning("Job board scrape failed for '%s' / '%s': %s", term, location, exc)
            time.sleep(1)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["dedup_key"] = combined.apply(_dedup_key, axis=1)
    return combined.drop_duplicates(subset=["dedup_key"], keep="first")


def _scrape_all_sources(cfg: dict) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    jobs = _scrape_job_boards(cfg)
    if not jobs.empty:
        frames.append(jobs)

    if cfg["scrape_linkedin_posts"]:
        posts = fetch_hiring_posts(
            cfg["search_terms"],
            cfg["search_locations"],
            max_results=cfg["linkedin_posts_max"],
        )
        if not posts.empty:
            frames.append(posts)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["dedup_key"] = combined.apply(_dedup_key, axis=1)
    combined = combined[combined["dedup_key"].astype(bool)]
    return combined.drop_duplicates(subset=["dedup_key"], keep="first")


def run_digest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = _config()
    posted_ids = _load_posted_ids()
    new_ids = set(posted_ids)

    logger.info(
        "Sources: %s job boards%s",
        ", ".join(cfg["job_sites"]),
        " + LinkedIn posts" if cfg["scrape_linkedin_posts"] else "",
    )
    jobs = _scrape_all_sources(cfg)

    if jobs.empty:
        logger.info("Scrape returned zero jobs — nothing to post.")
        return 0

    pending: list[tuple[str, pd.Series]] = []

    for _, row in jobs.iterrows():
        if len(pending) >= cfg["results_wanted"]:
            break
        if _should_skip(row, cfg["title_keywords"]):
            continue

        dedup_key = _dedup_key(row)
        if not dedup_key or dedup_key in posted_ids:
            continue

        pending.append((dedup_key, row))

    if not pending:
        logger.info("No new jobs this run — all listings were already posted.")
        return 0

    for dedup_key, _ in pending:
        new_ids.add(dedup_key)

    payload = _build_consolidated_message(pending, cfg)
    _send_message(cfg["token"], cfg["channel_id"], payload)
    _save_posted_ids(new_ids)

    logger.info("Digest finished — posted %s new jobs in one message.", len(pending))
    return len(pending)
