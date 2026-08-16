"""Shared suggestions storage backed by a private GitHub Gist.

Using a Gist instead of a local file means every viewer (and every redeploy
on Streamlit Community Cloud, which does not guarantee local disk persists)
reads/writes the same data.

Auth: needs a GitHub token with only the 'gist' scope, provided via
st.secrets["GITHUB_TOKEN"] (set in Streamlit Cloud's app Secrets) or the
GITHUB_TOKEN environment variable for local runs.
"""

import json
import os

import requests
import streamlit as st

GIST_ID = "7aeb471696a4f9a187dce24171a0fca7"
FILENAME = "suggestions.json"
API_URL = f"https://api.github.com/gists/{GIST_ID}"


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


def load_suggestions() -> list[dict]:
    try:
        resp = requests.get(API_URL, headers=_headers(), timeout=10)
        resp.raise_for_status()
        content = resp.json()["files"][FILENAME]["content"]
        return json.loads(content) if content.strip() else []
    except Exception as exc:  # noqa: BLE001
        st.warning(f"讀取家人建議失敗，稍後再試（{exc}）")
        return []


def save_suggestions(rows: list[dict]) -> bool:
    try:
        resp = requests.patch(
            API_URL,
            headers=_headers(),
            json={"files": {FILENAME: {"content": json.dumps(rows, ensure_ascii=False, indent=2)}}},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        st.error(f"儲存失敗，請稍後再試（{exc}）")
        return False
