"""Shared app state backed by a private GitHub Gist (multiple files in one gist).

Using a Gist instead of local files means every viewer (and every redeploy
on Streamlit Community Cloud, which does not guarantee local disk persists)
reads/writes the same data.

Auth: needs a GitHub token with only the 'Gists: Read and write' user
permission, provided via st.secrets["GITHUB_TOKEN"] (set in Streamlit
Cloud's app Secrets) or the GITHUB_TOKEN environment variable locally.
"""

import json
import os
from datetime import datetime

import requests
import streamlit as st

GIST_ID = "7aeb471696a4f9a187dce24171a0fca7"
API_URL = f"https://api.github.com/gists/{GIST_ID}"

FILES = {
    "suggestions": "suggestions.json",
    "votes": "votes.json",
    "todos": "todos.json",
    "maplog": "maplog.json",
}


def _token() -> str | None:
    try:
        if "GITHUB_TOKEN" in st.secrets:
            return st.secrets["GITHUB_TOKEN"]
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN")


def _headers() -> dict:
    token = _token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


@st.cache_data(ttl=8, show_spinner=False)
def _load_gist_files() -> dict:
    """Single cached fetch of the whole gist (all files at once), refreshed every 8s
    or immediately after any write via _save()'s cache.clear() call. This avoids
    hitting the GitHub API on every widget rerun (expander open/close etc.)."""
    resp = requests.get(API_URL, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()["files"]


def _load(key: str, default):
    filename = FILES[key]
    try:
        files = _load_gist_files()
        if filename not in files:
            return default
        content = files[filename]["content"]
        return json.loads(content) if content.strip() else default
    except Exception as exc:  # noqa: BLE001
        st.warning(f"讀取資料失敗，稍後再試（{exc}）")
        return default


def _save(key: str, data) -> bool:
    filename = FILES[key]
    try:
        resp = requests.patch(
            API_URL,
            headers=_headers(),
            json={"files": {filename: {"content": json.dumps(data, ensure_ascii=False, indent=2)}}},
            timeout=10,
        )
        resp.raise_for_status()
        _load_gist_files.clear()
        return True
    except Exception as exc:  # noqa: BLE001
        st.error(f"儲存失敗，請稍後再試（{exc}）")
        return False


def load_suggestions() -> list[dict]:
    return _load("suggestions", [])


def save_suggestions(rows: list[dict]) -> bool:
    return _save("suggestions", rows)


def load_votes() -> list[dict]:
    """Each vote record: {item_id, item_type, voter, time}."""
    return _load("votes", [])


def save_votes(rows: list[dict]) -> bool:
    return _save("votes", rows)


def load_todos() -> dict:
    """Map of todo id -> bool (done)."""
    return _load("todos", {})


def save_todos(state: dict) -> bool:
    return _save("todos", state)


def load_maplog() -> dict:
    """Monthly Google Maps JS load counter: {"month": "YYYY-MM", "count": int}.
    Not yet called from app.py — scaffolding for the Phase B soft-cap fallback
    (see project memory notes on the Google Maps migration)."""
    return _load("maplog", {"month": "", "count": 0})


def save_maplog(state: dict) -> bool:
    return _save("maplog", state)


def bump_maplog() -> dict:
    """Increment this month's counter, resetting automatically on month rollover.
    Returns the updated state so callers can compare it against a soft-cap threshold."""
    now_month = datetime.now().strftime("%Y-%m")
    state = load_maplog()
    if state.get("month") != now_month:
        state = {"month": now_month, "count": 0}
    state["count"] += 1
    save_maplog(state)
    return state
