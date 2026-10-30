"""2027 東京家族旅遊 — 互動行程網頁

跑法： streamlit run app.py --server.headless true
"""

from collections import defaultdict
from datetime import datetime
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gist_store
from data import (
    ATTRACTION_CANDIDATES,
    DAYS,
    FLIGHTS,
    FOOD_CANDIDATES,
    HOTELS,
    TODOS,
    TRANSPORT,
    TRANSPORT_NOTE,
)

st.set_page_config(page_title="2027 東京家族旅遊", page_icon="🗾", layout="wide")

if "voter_name" not in st.session_state:
    st.session_state.voter_name = ""


def render_voter_name_input(tab_key: str):
    field_key = f"voter_name_input_{tab_key}"
    name = st.text_input(
        "你是誰（選填——填了會記錄是誰投的，不填就算匿名，一樣可以投票）",
        value=st.session_state.voter_name,
        key=field_key,
    )
    st.session_state.voter_name = name
    return name.strip()


def render_vote_controls(votes: list[dict], item_id: str, item_type: str, voter: str, count: int, key_prefix: str):
    col_minus, col_count, col_plus = st.columns([1, 1, 1])
    with col_minus:
        if st.button("➖", key=f"{key_prefix}_minus", use_container_width=True, disabled=count <= 0):
            for i in range(len(votes) - 1, -1, -1):
                if votes[i]["item_id"] == item_id and votes[i]["item_type"] == item_type:
                    del votes[i]
                    break
            if gist_store.save_votes(votes):
                st.rerun()
    with col_count:
        st.markdown(
            f"<div style='text-align:center;font-weight:800;font-size:1.6em;line-height:2.2em'>{count}</div>",
            unsafe_allow_html=True,
        )
    with col_plus:
        if st.button("➕", key=f"{key_prefix}_plus", use_container_width=True, type="primary"):
            votes.append(
                {
                    "item_id": item_id,
                    "item_type": item_type,
                    "voter": voter or "匿名",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            )
            if gist_store.save_votes(votes):
                st.rerun()


def render_vote_section(candidates: list[dict], item_type: str, voter: str):
    votes = gist_store.load_votes()
    counts = defaultdict(int)
    for v in votes:
        if v.get("item_type") != item_type:
            continue
        counts[v["item_id"]] += 1

    areas = sorted({c["area"] for c in candidates}, key=lambda a: [c["area"] for c in candidates].index(a))
    for area in areas:
        area_items = [c for c in candidates if c["area"] == area]
        area_votes = sum(counts.get(c["id"], 0) for c in area_items)
        badge = f"　🗳️ {area_votes}票" if area_votes else ""
        with st.expander(f"**{area}**{badge}", expanded=False):
            for cand in area_items:
                col1, col2 = st.columns([4, 2])
                search_url = f"https://www.google.com/search?q={quote(cand['name'])}"
                with col1:
                    st.markdown(
                        f"**{cand['name']}** <a href='{search_url}' target='_blank' rel='noopener noreferrer'>🔗</a>",
                        unsafe_allow_html=True,
                    )
                if cand.get("scheduled_day"):
                    with col2:
                        st.caption(f"✅ Day {cand['scheduled_day']}")
                    continue
                with col2:
                    render_vote_controls(
                        votes, cand["id"], item_type, voter, counts.get(cand["id"], 0), f"{item_type}_{cand['id']}"
                    )


def render_food_vote_section(candidates: list[dict], voter: str):
    votes = gist_store.load_votes()
    counts = defaultdict(int)
    for v in votes:
        if v.get("item_type") != "food":
            continue
        counts[v["item_id"]] += 1

    regions = sorted({c["region"] for c in candidates}, key=lambda r: [c["region"] for c in candidates].index(r))

    def _region_label(r):
        total = sum(counts.get(c["id"], 0) for c in candidates if c["region"] == r)
        return f"{r}　🗳️{total}" if total else r

    region = st.radio("選地區（🗳️旁邊數字是這區目前總票數）", regions, horizontal=True, key="food_region", format_func=_region_label)

    region_items = [c for c in candidates if c["region"] == region]
    categories = sorted(
        {c["category"] for c in region_items}, key=lambda x: [c["category"] for c in region_items].index(x)
    )
    for category in categories:
        cat_items = [c for c in region_items if c["category"] == category]
        cat_votes = sum(counts.get(c["id"], 0) for c in cat_items)
        badge = f"　🗳️ {cat_votes}票" if cat_votes else ""
        with st.expander(f"**{category}**（{len(cat_items)}家）{badge}", expanded=False):
            for cand in cat_items:
                col1, col2 = st.columns([4, 2])
                with col1:
                    search_url = f"https://www.google.com/search?q={quote(cand['name'] + ' ' + cand['location'])}"
                    st.markdown(
                        f"**{cand['name']}** <a href='{search_url}' target='_blank' rel='noopener noreferrer'>🔗</a>　"
                        f"<span style='color:gray;font-size:0.85em'>📍{cand['location']}・{cand['note']}</span>",
                        unsafe_allow_html=True,
                    )
                with col2:
                    render_vote_controls(votes, cand["id"], "food", voter, counts.get(cand["id"], 0), f"food_{cand['id']}")


st.title("🗾 2027 東京家族旅遊 1/21–1/29")
st.caption("11人・全員iPhone・這頁大家都能看到同一份內容，投票/許願會即時同步")

todo_state = gist_store.load_todos()
_todo_dirty = []


def render_todo_checkbox(item: dict) -> None:
    """Interactive checkbox for one TODOS entry, backed by gist_store (shared across everyone)."""
    current = todo_state.get(item["id"], item["default_done"])
    checked = st.checkbox(item["text"], value=current, key=f"todo_{item['id']}")
    if item.get("url"):
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🔗 [{item['url']}]({item['url']})")
    if checked != current:
        todo_state[item["id"]] = checked
        _todo_dirty.append(True)


tab_itinerary, tab_food, tab_spot, tab_wish = st.tabs(
    ["📅 逐日行程", "🍜 美食投票", "🎡 景點投票", "🌟 許願池"]
)

with tab_itinerary:
    with st.container(border=True):
        st.markdown("#### ✈️ 機票")
        for f in FLIGHTS:
            st.markdown(f"- **{f['flight']}**　{f['date']}　{f['route']}　{f['time']}")

        st.markdown("#### 🏨 住宿")
        for h in HOTELS:
            st.markdown(
                f"- **{h['name']}**（{h['dates']}）\n"
                f"　　📍{h['address']}　☎️{h['phone']}"
            )

        st.markdown("#### 🚗 日本交通")
        for t in TRANSPORT:
            st.markdown(f"- **{t['date']}**　{t['text']}")
        st.caption(TRANSPORT_NOTE)

        st.markdown("#### 🚇 官方地鐵路線圖")
        st.caption("資訊較多，適合要查確切站名/轉乘方式時再點開")
        with st.expander("繁體中文版（含站號，2023.05，建議當主要參考）"):
            st.image("assets/metro_map_tcn.png", width="stretch")
        with st.expander("日文版（2020.06，備用對照）"):
            st.image("assets/metro_map_ja.png", width="stretch")

    for d in DAYS:
        with st.expander(f"Day {d['day']}・{d['date']}　{d['title']}　{d['status']}", expanded=False):
            if d.get("transit"):
                st.info(d["transit"])
            for item in d["items"]:
                st.markdown(f"- {item}")
            day_todos = [t for t in TODOS if t.get("day") == d["day"]]
            if day_todos:
                st.markdown("**待辦：**")
                for t in day_todos:
                    render_todo_checkbox(t)

with tab_food:
    st.markdown("### 美食投票")
    st.caption("246家具體店家，先選地區再選分類；把想吃的都投一票，我會根據票數安排對應那天的用餐地點。名單裡沒有的想吃什麼，去「許願池」填")
    voter = render_voter_name_input("food")
    render_food_vote_section(FOOD_CANDIDATES, voter)

with tab_spot:
    st.markdown("### 景點投票")
    st.caption("投票高的會優先安插進行程；名單裡沒有的想去哪裡，去「許願池」填")
    voter = render_voter_name_input("attraction")
    render_vote_section(ATTRACTION_CANDIDATES, "attraction", voter)

with tab_wish:
    st.markdown("### 🌟 許願池")
    st.caption("候選清單沒有的地方，想去哪裡都可以在這裡許願；其他人也可以幫你的願望+1")

    with st.form("wish_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            submitted_by = st.text_input("你是誰（名字）")
            place_name = st.text_input("地點名稱（越具體越好，例如「歌舞伎町一番街」）")
        with col2:
            day_pref = st.selectbox(
                "偏好排在哪天（不確定可選「都可以」）",
                ["都可以"] + [f"Day {d['day']}（{d['date']}）" for d in DAYS],
            )
            note = st.text_area("備註（為什麼想去/想吃什麼）", height=80)
        submitted = st.form_submit_button("送出願望")

    if submitted:
        if not place_name.strip():
            st.warning("地點名稱不能空白喔")
        else:
            rows = gist_store.load_suggestions()
            rows.append(
                {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "提交人": submitted_by or "匿名",
                    "地點": place_name,
                    "備註": note,
                    "偏好Day": day_pref,
                }
            )
            if gist_store.save_suggestions(rows):
                st.success("許願成功！")
                st.rerun()

    st.markdown("---")
    st.markdown("### 目前所有願望")
    current_rows = gist_store.load_suggestions()
    if not current_rows:
        st.caption("還沒有人許願，第一個來寫吧！")
    else:
        st.dataframe(
            pd.DataFrame(current_rows)[["時間", "提交人", "地點", "偏好Day", "備註"]],
            use_container_width=True,
            hide_index=True,
        )

if _todo_dirty:
    gist_store.save_todos(todo_state)
    st.rerun()

