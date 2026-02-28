"""
github_check.py — Checks if the user has made at least one GitHub commit today.
"""

import datetime
import requests
from shared import load_config, log, decrypt_token


def has_commit_today() -> tuple[bool, str]:
    """
    Returns (True, reason) if user has a commit today, (False, reason) otherwise.
    Uses the GitHub Events API — no special scope needed for public activity.
    Falls back to Search API with a token if provided.
    """
    cfg = load_config()
    username = cfg.get("github_username", "").strip()
    token    = decrypt_token(cfg.get("github_token", "")).strip()

    if not username:
        return False, "GitHub username not configured."

    today = datetime.date.today()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # ── Method 1: Events API (fast, no token required for public repos) ────────
    # Returns up to 300 most recent public events (enough for active users)
    try:
        url = f"https://api.github.com/users/{username}/events"
        resp = requests.get(url, headers=headers, timeout=10, params={"per_page": 100})
        if resp.status_code == 200:
            events = resp.json()
            for event in events:
                if event.get("type") not in ("PushEvent", "CreateEvent"):
                    continue
                created_at = event.get("created_at", "")
                event_date_str = created_at[:10]  # "YYYY-MM-DD"
                try:
                    event_date = datetime.date.fromisoformat(event_date_str)
                except ValueError:
                    continue
                if event_date == today:
                    repo = event.get("repo", {}).get("name", "unknown repo")
                    log(f"GitHub: Found commit/push today in {repo}")
                    return True, f"Commit found in {repo} today ✓"
            # Events loaded but none today
            log("GitHub: Events API — no push/commit found today.")
        else:
            log(f"GitHub Events API returned {resp.status_code}")
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
                    log(f"GitHub Search: Found {total} commit(s) today.")
                    return True, f"{total} commit(s) found today ✓"
                else:
                    log("GitHub Search: No commits found today.")
            else:
                log(f"GitHub Search API returned {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            log(f"GitHub Search API error: {e}")

    return False, "No GitHub commits found today."
