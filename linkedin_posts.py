import hashlib
import logging
import re
import time

import pandas as pd

logger = logging.getLogger("job_digest")

POST_URL_MARKERS = ("/posts/", "/pulse/", "/feed/update/")


def _post_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"post-{digest}"


def _guess_company(title: str, body: str) -> str:
    text = f"{title} {body}"
    match = re.search(r"at\s+([A-Z][A-Za-z0-9&.\- ]{2,40})", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"#([A-Za-z][A-Za-z0-9_]{2,30})", text)
    if match:
        return match.group(1).replace("_", " ")
    return "See post"


def _is_post_url(url: str) -> bool:
    url_lower = url.lower()
    if "/jobs/" in url_lower:
        return False
    return any(marker in url_lower for marker in POST_URL_MARKERS)


def fetch_hiring_posts(
    search_terms: list[str],
    search_locations: list[str],
    max_results: int = 20,
) -> pd.DataFrame:
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs not installed — skipping LinkedIn hiring posts.")
        return pd.DataFrame()

    rows: list[dict] = []
    seen_urls: set[str] = set()
    cities = list(dict.fromkeys(loc.split(",")[0].strip() for loc in search_locations if loc.strip()))

    try:
        ddgs = DDGS()
    except Exception as exc:
        logger.warning("Could not init DDGS: %s", exc)
        return pd.DataFrame()

    for term in search_terms:
        for city in cities:
            if len(rows) >= max_results:
                break
            query = f'site:linkedin.com/posts OR site:linkedin.com/pulse "{term}" hiring {city} India'
            logger.info("Searching LinkedIn posts: %s", query)
            try:
                results = ddgs.text(query, max_results=5)
            except Exception as exc:
                logger.warning("LinkedIn post search failed for %r: %s", query, exc)
                time.sleep(1)
                continue

            for item in results:
                url = str(item.get("href", "")).strip()
                if not url or url in seen_urls or not _is_post_url(url):
                    continue

                title = str(item.get("title", "LinkedIn hiring post")).strip()[:256]
                body = str(item.get("body", "")).strip()
                seen_urls.add(url)
                rows.append(
                    {
                        "id": _post_id(url),
                        "site": "linkedin_post",
                        "title": title,
                        "company": _guess_company(title, body),
                        "job_url": url,
                        "job_url_direct": url,
                        "date_posted": None,
                    }
                )
                if len(rows) >= max_results:
                    break
            time.sleep(0.8)

    logger.info("Found %s LinkedIn hiring posts.", len(rows))
    return pd.DataFrame(rows)
