"""2027 東京家族旅遊 — 互動行程網頁

跑法： streamlit run app.py --server.headless true
"""

from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import gist_store
from data import CANDIDATE_SPOTS, DAYS, SPOTS

DAY_COLORS = {
    1: "cadetblue", 2: "cadetblue", 3: "cadetblue",
    4: "orange", 5: "orange", 6: "orange",
    7: "orange", 8: "orange", 9: "cadetblue",
}

st.set_page_config(page_title="2027 東京家族旅遊", page_icon="🗾", layout="wide")


SUGGESTION_COLUMNS = ["時間", "提交人", "地點", "備註", "偏好Day", "緯度", "經度", "定位狀態"]


def load_suggestions() -> pd.DataFrame:
    rows = gist_store.load_suggestions()
    if not rows:
        return pd.DataFrame(columns=SUGGESTION_COLUMNS)
    return pd.DataFrame(rows)


def save_suggestion(row: dict) -> bool:
    rows = gist_store.load_suggestions()
    rows.append(row)
    return gist_store.save_suggestions(rows)


def geocode_place(place_name: str):
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="tokyo-2027-family-trip-app")
        location = geolocator.geocode(f"{place_name}, Japan", timeout=8)
        if location:
            return location.latitude, location.longitude, "成功定位"
        return None, None, "找不到位置，已收到建議但地圖上不會顯示"
    except Exception:
        return None, None, "定位服務暫時無法使用，已收到建議但地圖上不會顯示"


st.title("🗾 2027 東京家族旅遊 1/21–1/29")
st.caption("11人・全員iPhone・這頁大家都能看到同一份內容，家人建議會即時同步")

tab_itinerary, tab_map, tab_suggest = st.tabs(["📅 逐日行程", "🗺️ 地圖", "💡 家人建議"])

with tab_itinerary:
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
    st.markdown("藍色＝富士山/河口湖區（Day1–3），橘色＝東京都心（Day4–8），紫色＝家人建議地點")

    m = folium.Map(location=[35.68, 139.55], zoom_start=9, tiles="OpenStreetMap")

    for spot in SPOTS:
        folium.Marker(
            location=[spot["lat"], spot["lon"]],
            popup=f"<b>{spot['name']}</b><br>Day {spot['day']}・{spot['category']}",
            tooltip=spot["name"],
            icon=folium.Icon(color=DAY_COLORS.get(spot["day"], "gray"), icon="info-sign"),
        ).add_to(m)

    for cand in CANDIDATE_SPOTS:
        folium.Marker(
            location=[cand["lat"], cand["lon"]],
            popup=f"<b>{cand['name']}</b><br>{cand['note']}",
            tooltip=f"{cand['name']}（候選）",
            icon=folium.Icon(color="lightgray", icon="question-sign"),
        ).add_to(m)

    suggestions_df = load_suggestions()
    valid_suggestions = suggestions_df.dropna(subset=["緯度", "經度"]) if not suggestions_df.empty else suggestions_df
    for _, row in valid_suggestions.iterrows():
        folium.Marker(
            location=[row["緯度"], row["經度"]],
            popup=f"<b>{row['地點']}</b><br>{row['提交人']} 提議<br>{row.get('備註', '')}",
            tooltip=f"💡 {row['地點']}",
            icon=folium.Icon(color="purple", icon="star"),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=600, returned_objects=[])

with tab_suggest:
    st.markdown("### 提議想去的地方")
    st.caption("填完送出後，大家（包含地圖分頁）都會看到你加的地點")

    with st.form("suggestion_form", clear_on_submit=True):
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
        submitted = st.form_submit_button("送出建議")

    if submitted:
        if not place_name.strip():
            st.warning("地點名稱不能空白喔")
        else:
            with st.spinner("定位中..."):
                lat, lon, geo_status = geocode_place(place_name)
            ok = save_suggestion(
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
            if ok:
                st.success(f"已加入！{geo_status}")
                st.rerun()

    st.markdown("---")
    st.markdown("### 目前所有建議")
    current = load_suggestions()
    if current.empty:
        st.caption("還沒有人提議，第一個來寫吧！")
    else:
        st.dataframe(
            current[["時間", "提交人", "地點", "偏好Day", "備註", "定位狀態"]],
            use_container_width=True,
            hide_index=True,
        )
