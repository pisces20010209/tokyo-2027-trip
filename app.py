"""2027 東京家族旅遊 — 互動行程網頁

跑法： streamlit run app.py --server.headless true
"""

import hashlib
import html
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import gist_store
from data import ATTRACTION_CANDIDATES, CANDIDATE_SPOTS, DAYS, FLIGHTS, FOOD_CANDIDATES, HOTELS, SPOTS, TODOS

DAY_COLORS = {
    1: "cadetblue", 2: "cadetblue", 3: "cadetblue",
    4: "orange", 5: "orange", 6: "orange",
    7: "orange", 8: "orange", 9: "cadetblue",
}

# High-saturation marker colors for the Google Maps pin path — picked to stay
# readable against Google's own colorful basemap (parks/water/POI icons),
# which washed out the original folium-matched muted tones (cadetblue, etc.).
_DAY_COLOR_HEX = {"cadetblue": "#1565C0", "orange": "#E65100"}
_CANDIDATE_COLOR_HEX = "#616161"
_SUGGESTION_COLOR_HEX = "#8E24AA"

# 80% of Maps Platform's Essentials-tier free allowance (10,000 map loads/month).
# Above this, render_map() falls back to the free OpenStreetMap/folium map instead
# of initializing Google Maps JS, so we never actually reach Google's billed tier.
GOOGLE_SOFT_CAP = 8000

# Requires [server] enableStaticServing = true in .streamlit/config.toml.
_STATIC_DIR = Path(__file__).parent / "static"

st.set_page_config(page_title="2027 東京家族旅遊", page_icon="🗾", layout="wide")

if "voter_name" not in st.session_state:
    st.session_state.voter_name = ""


def _google_maps_api_key() -> str:
    try:
        if "GOOGLE_MAPS_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_MAPS_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GOOGLE_MAPS_API_KEY", "")


def geocode_place(place_name: str):
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="tokyo-2027-family-trip-app")
        location = geolocator.geocode(f"{place_name}, Japan", timeout=8)
        if location:
            return location.latitude, location.longitude, "成功定位"
        return None, None, "找不到位置，已收到願望但地圖上不會顯示"
    except Exception:
        return None, None, "定位服務暫時無法使用，已收到願望但地圖上不會顯示"


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


def _suggestions_fingerprint(suggestions: list[dict]) -> int:
    """Change-detector for gist wish-pool data; hashes content rather than just
    len() since existing entries could in principle be edited, not just appended."""
    return hash(json.dumps(suggestions, sort_keys=True, ensure_ascii=False))


def _build_folium_map(picked_regions: list[str], suggestions: list[dict]) -> folium.Map:
    """Pure builder, no Streamlit calls inside. This is the one function a future
    Google Maps swap-in replaces/wraps; render_map() controls when it gets called."""
    m = folium.Map(location=[35.68, 139.55], zoom_start=9, tiles="OpenStreetMap")

    for spot in SPOTS:
        folium.Marker(
            location=[spot["lat"], spot["lon"]],
            popup=folium.Popup(f"<b>{spot['name']}</b><br>Day {spot['day']}・{spot['category']}", max_width=260),
            tooltip=spot["name"],
            icon=folium.Icon(color=DAY_COLORS.get(spot["day"], "gray"), icon="info-sign"),
        ).add_to(m)

    for cand in CANDIDATE_SPOTS:
        folium.Marker(
            location=[cand["lat"], cand["lon"]],
            popup=folium.Popup(f"<b>{cand['name']}</b><br>{cand['note']}", max_width=260),
            tooltip=f"{cand['name']}（候選）",
            icon=folium.Icon(color="lightgray", icon="question-sign"),
        ).add_to(m)

    if picked_regions:
        for cand in ATTRACTION_CANDIDATES:
            if cand["area"] not in picked_regions or cand["lat"] is None:
                continue
            if cand.get("scheduled_day"):
                continue  # already shown via SPOTS with its day color
            folium.Marker(
                location=[cand["lat"], cand["lon"]],
                popup=folium.Popup(f"<b>{cand['name']}</b><br>{cand['area']}・尚未排入行程", max_width=260),
                tooltip=f"{cand['name']}（候選）",
                icon=folium.Icon(color="lightgray", icon="question-sign"),
            ).add_to(m)

    suggestions_df = pd.DataFrame(suggestions)
    if not suggestions_df.empty and "緯度" in suggestions_df.columns:
        valid_suggestions = suggestions_df.dropna(subset=["緯度", "經度"])
        for _, row in valid_suggestions.iterrows():
            folium.Marker(
                location=[row["緯度"], row["經度"]],
                popup=folium.Popup(
                    f"<b>{row['地點']}</b><br>{row['提交人']} 許願<br>{row.get('備註', '')}", max_width=260
                ),
                tooltip=f"🌟 {row['地點']}",
                icon=folium.Icon(color="purple", icon="star"),
            ).add_to(m)

    return m


def _build_google_map_html(picked_regions: list[str], suggestions: list[dict], api_key: str) -> str:
    """Google Maps JS equivalent of _build_folium_map(), same data/filtering rules.
    Marker colors are drawn with google.maps.SymbolPath.CIRCLE (exact hex fill)
    instead of relying on any external icon URL. All user-submitted text (wish
    suggestions) is HTML-escaped before being embedded in an InfoWindow, since
    that content renders as innerHTML in the browser."""
    markers = []

    for spot in SPOTS:
        color = _DAY_COLOR_HEX.get(DAY_COLORS.get(spot["day"], "orange"), "#808080")
        markers.append(
            {
                "lat": spot["lat"],
                "lng": spot["lon"],
                "info": f"<b>{html.escape(spot['name'])}</b><br>Day {spot['day']}・{html.escape(spot['category'])}",
                "color": color,
            }
        )

    for cand in CANDIDATE_SPOTS:
        markers.append(
            {
                "lat": cand["lat"],
                "lng": cand["lon"],
                "info": f"<b>{html.escape(cand['name'])}</b><br>{html.escape(cand['note'])}",
                "color": _CANDIDATE_COLOR_HEX,
            }
        )

    if picked_regions:
        for cand in ATTRACTION_CANDIDATES:
            if cand["area"] not in picked_regions or cand["lat"] is None:
                continue
            if cand.get("scheduled_day"):
                continue  # already shown via SPOTS with its day color
            markers.append(
                {
                    "lat": cand["lat"],
                    "lng": cand["lon"],
                    "info": f"<b>{html.escape(cand['name'])}</b><br>{html.escape(cand['area'])}・尚未排入行程",
                    "color": _CANDIDATE_COLOR_HEX,
                }
            )

    for row in suggestions:
        lat, lon = row.get("緯度"), row.get("經度")
        if lat is None or lon is None:
            continue
        place = html.escape(str(row.get("地點", "")))
        submitter = html.escape(str(row.get("提交人", "")))
        note = html.escape(str(row.get("備註", "") or ""))
        markers.append(
            {
                "lat": lat,
                "lng": lon,
                "info": f"<b>{place}</b><br>{submitter} 許願<br>{note}",
                "color": _SUGGESTION_COLOR_HEX,
            }
        )

    markers_json = json.dumps(markers, ensure_ascii=False)
    safe_api_key = html.escape(api_key, quote=True)

    return f"""
<div id="google_map" style="width:100%;height:600px;"></div>
<script>
  function initMap() {{
    const map = new google.maps.Map(document.getElementById("google_map"), {{
      center: {{lat: 35.68, lng: 139.55}},
      zoom: 9,
    }});
    const infoWindow = new google.maps.InfoWindow();
    const markers = {markers_json};
    // Material "place" pin outline (24x24 viewBox), tip anchored at the exact
    // coordinate. A teardrop pin reads much better against Google's own
    // colorful basemap than a flat dot, and matches what people expect from
    // map pins generally.
    const PIN_PATH =
      "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z";
    markers.forEach(function (m) {{
      const marker = new google.maps.Marker({{
        position: {{lat: m.lat, lng: m.lng}},
        map: map,
        icon: {{
          path: PIN_PATH,
          fillColor: m.color,
          fillOpacity: 1,
          scale: 1.8,
          strokeWeight: 1.5,
          strokeColor: "#ffffff",
          anchor: new google.maps.Point(12, 22),
        }},
      }});
      marker.addListener("click", function () {{
        infoWindow.setContent(m.info);
        infoWindow.open(map, marker);
      }});
    }});
  }}
</script>
<script src="https://maps.googleapis.com/maps/api/js?key={safe_api_key}&callback=initMap&loading=async" async defer></script>
"""


def _write_google_map_static(html_content: str) -> str:
    """Writes the map HTML to a real file under static/ (Streamlit's static file
    serving) and returns its relative URL, instead of embedding the HTML string
    directly via iframe srcdoc. Google's HTTP-referrer key restriction needs a
    real page URL to check against — an srcdoc iframe reports "about:srcdoc" as
    its origin, which the restriction can never match, so the API key would
    have to go unrestricted to work at all. Filename is a content hash so
    identical map states (e.g. the same picked_regions filter picked by two
    different family members) reuse one file instead of colliding or piling up."""
    _STATIC_DIR.mkdir(exist_ok=True)
    digest = hashlib.md5(html_content.encode("utf-8")).hexdigest()[:12]
    filename = f"map_{digest}.html"
    path = _STATIC_DIR / filename
    if not path.exists():
        path.write_text(html_content, encoding="utf-8")
    return f"/app/static/{filename}"


def render_map() -> None:
    """Map tab body. Uses Google Maps JS when GOOGLE_MAPS_API_KEY is configured
    and this month's usage (tracked via gist_store's maplog counter) is under
    GOOGLE_SOFT_CAP; otherwise falls back to the free OpenStreetMap/folium map,
    so a map is always shown either way.

    State-gated: only rebuilds the map object (and bumps the debug render
    counter / gist_store.bump_maplog() for the Google path) when picked_regions,
    the gist suggestions data, or the active mode actually changed since the
    last render this session — an unrelated rerun (e.g. a vote click in another
    tab, since st.tabs() re-executes every tab's body on every rerun) reuses the
    cached map object instead of rebuilding it.

    Caveat: st_folium is a proper declared Streamlit component with its own
    remount semantics, while the Google path uses st.iframe(...) with a raw
    HTML string, which behaves differently. This state-gating pattern narrows
    the risk, but
    whether it actually prevents extra Google "map load" billing events on
    every unrelated rerun can only be confirmed via a real browser DevTools
    Network-tab check (see project memory notes on the Google Maps migration
    for the full verification plan)."""
    st.markdown("藍色＝富士山/河口湖區（Day1–3），橘色＝東京都心（Day4–8），灰色＝還沒排進行程的候選景點，紫色＝許願池地點")

    candidate_regions = sorted(
        {c["area"] for c in ATTRACTION_CANDIDATES if c["lat"] is not None},
        key=lambda a: [c["area"] for c in ATTRACTION_CANDIDATES if c["lat"] is not None].index(a),
    )
    picked_regions = st.multiselect(
        "要在地圖上加顯示哪些地區的候選景點？（還沒排進行程的，灰色標記）",
        candidate_regions,
        default=[],
        key="map_picked_regions",
    )

    suggestions = gist_store.load_suggestions()
    signature = (tuple(sorted(picked_regions)), _suggestions_fingerprint(suggestions))

    api_key = _google_maps_api_key()
    maplog = gist_store.load_maplog()
    current_month = datetime.now().strftime("%Y-%m")
    count_this_month = maplog["count"] if maplog.get("month") == current_month else 0
    use_google = bool(api_key) and count_this_month < GOOGLE_SOFT_CAP
    mode = "google" if use_google else "folium"

    needs_rebuild = (
        st.session_state.get("_map_signature") != signature
        or st.session_state.get("_map_mode") != mode
        or "_map_obj" not in st.session_state
    )
    if needs_rebuild:
        if use_google:
            html_content = _build_google_map_html(picked_regions, suggestions, api_key)
            st.session_state["_map_obj"] = _write_google_map_static(html_content)
            gist_store.bump_maplog()
        else:
            st.session_state["_map_obj"] = _build_folium_map(picked_regions, suggestions)
        st.session_state["_map_signature"] = signature
        st.session_state["_map_mode"] = mode
        st.session_state["_map_render_count"] = st.session_state.get("_map_render_count", 0) + 1

    if mode == "google":
        st.iframe(st.session_state["_map_obj"], height=600)
    else:
        st_folium(
            st.session_state["_map_obj"],
            use_container_width=True,
            height=600,
            returned_objects=[],
            key="tokyo_map",
        )
        if api_key and count_this_month >= GOOGLE_SOFT_CAP:
            st.caption("⚠️ 本月Google地圖用量已達軟上限，暫時顯示備用版OpenStreetMap地圖")

    if st.query_params.get("debug") == "1":
        st.caption(f"debug: map (re)built {st.session_state['_map_render_count']}x this session (mode={mode})")

    st.markdown("### 官方地鐵路線圖")
    st.caption("資訊較多，適合要查確切站名/轉乘方式時再點開")
    with st.expander("繁體中文版（含站號，2023.05，建議當主要參考）"):
        st.image("assets/metro_map_tcn.png", width="stretch")
    with st.expander("日文版（2020.06，備用對照）"):
        st.image("assets/metro_map_ja.png", width="stretch")


st.title("🗾 2027 東京家族旅遊 1/21–1/29")
st.caption("11人・全員iPhone・這頁大家都能看到同一份內容，投票/許願會即時同步")

tab_itinerary, tab_map, tab_food, tab_spot, tab_wish, tab_todo = st.tabs(
    ["📅 逐日行程", "🗺️ 地圖", "🍜 美食投票", "🎡 景點投票", "🌟 許願池", "✅ 待辦清單"]
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

    for d in DAYS:
        with st.container(border=True):
            head_col1, head_col2 = st.columns([5, 1])
            with head_col1:
                st.subheader(f"Day {d['day']}・{d['date']}　{d['title']}")
            with head_col2:
                st.markdown(f"**{d['status']}**")
            if d.get("transit"):
                st.info(d["transit"])
            for item in d["items"]:
                st.markdown(f"- {item}")

with tab_map:
    render_map()

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
            with st.spinner("定位中..."):
                lat, lon, geo_status = geocode_place(place_name)
            rows = gist_store.load_suggestions()
            rows.append(
                {
                    "時間": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "提交人": submitted_by or "匿名",
                    "地點": place_name,
                    "備註": note,
                    "偏好Day": day_pref,
                    "緯度": lat,
                    "經度": lon,
                    "定位狀態": geo_status,
                }
            )
            if gist_store.save_suggestions(rows):
                st.success(f"許願成功！{geo_status}")
                st.rerun()

    st.markdown("---")
    st.markdown("### 目前所有願望")
    current_rows = gist_store.load_suggestions()
    if not current_rows:
        st.caption("還沒有人許願，第一個來寫吧！")
    else:
        st.dataframe(
            pd.DataFrame(current_rows)[["時間", "提交人", "地點", "偏好Day", "備註", "定位狀態"]],
            use_container_width=True,
            hide_index=True,
        )

with tab_todo:
    st.markdown("### ✅ 待辦清單")
    st.caption("誰都可以打勾，狀態大家共用")

    todo_state = gist_store.load_todos()
    changed = False
    for item in TODOS:
        current = todo_state.get(item["id"], item["default_done"])
        checked = st.checkbox(item["text"], value=current, key=f"todo_{item['id']}")
        if checked != current:
            todo_state[item["id"]] = checked
            changed = True
    if changed:
        gist_store.save_todos(todo_state)
        st.rerun()
