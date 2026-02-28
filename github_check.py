"""
github_check.py — Checks if the user has made at least one GitHub commit today.

All date comparisons are done in UTC to match GitHub's API timestamps.
The Events API returns up to 300 events (3 pages × 100); we paginate and
stop early once we either find a today-commit or hit an event from before today.
"""

import datetime
import requests
from shared import load_config, log, decrypt_token

# GitHub caps the Events API at 3 pages (300 events total).
_EVENTS_MAX_PAGES = 3


def _today_utc() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def _parse_event_date(created_at: str) -> datetime.date | None:
    """Parse a GitHub ISO-8601 UTC timestamp (e.g. '2024-01-15T10:30:00Z') to a UTC date."""
    try:
        dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return dt.date()
    except (ValueError, AttributeError):
        return None


def has_commit_today() -> tuple[bool, str]:
    """
    Returns (True, reason) if the user has a commit/push today (UTC), else (False, reason).

    Method 1 – Events API: fast, no token needed for public activity; paginated.
    Method 2 – Search API: requires token; catches private-repo commits.
    """
    cfg = load_config()
    username = cfg.get("github_username", "").strip()
    token = decrypt_token(cfg.get("github_token", "")).strip()

    if not username:
        return False, "GitHub username not configured."

    today = _today_utc()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # ── Method 1: Events API (paginated) ─────────────────────────────────────
    try:
        url = f"https://api.github.com/users/{username}/events"
        for page in range(1, _EVENTS_MAX_PAGES + 1):
            resp = requests.get(
                url, headers=headers, timeout=10,
                params={"per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                log(f"GitHub Events API page {page} returned {resp.status_code}")
                break

            events = resp.json()
            if not events:
                break  # No more events on this page

            stop_after_page = False
            for event in events:
                event_date = _parse_event_date(event.get("created_at", ""))
                if event_date is None:
                    continue

                if event_date < today:
                    # Events are newest-first; everything from here is older than today.
                    stop_after_page = True
                    break

                if event_date == today and event.get("type") in ("PushEvent", "CreateEvent"):
                    repo = event.get("repo", {}).get("name", "unknown repo")
                    log(f"GitHub Events: found push/commit today in {repo} (page {page})")
                    return True, f"Commit found in {repo} today ✓"

            if stop_after_page:
                break  # No point fetching older pages

        log("GitHub Events API: no push/commit found today.")
    except requests.RequestException as e:
        log(f"GitHub Events API error: {e}")

    # ── Method 2: Search API (requires token, catches private repos) ──────────
    if token:
        try:
            today_iso = today.isoformat()
            search_url = "https://api.github.com/search/commits"
            search_headers = dict(headers)
            search_headers["Accept"] = "application/vnd.github.cloak-preview+json"
            params = {"q": f"author:{username} author-date:{today_iso}", "per_page": 1}
            r = requests.get(search_url, headers=search_headers, timeout=10, params=params)
            if r.status_code == 200:
                total = r.json().get("total_count", 0)
                if total > 0:
                    log(f"GitHub Search: found {total} commit(s) today (UTC).")
                    return True, f"{total} commit(s) found today ✓"
                log("GitHub Search: no commits found today (UTC).")
            else:
                log(f"GitHub Search API returned {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            log(f"GitHub Search API error: {e}")

    return False, "No GitHub commits found today."
