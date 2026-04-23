import json

import leafmap.foliumap as leafmap
import requests
import streamlit as st

st.set_page_config(page_title="🌳 Deforestation Detector", layout="wide")

BACKEND = "http://127.0.0.1:8000"

st.title("🌍 Land Use & Deforestation Change Detection")
st.markdown(
    "Draw a region of interest (ROI) and compare land changes between two years."
)

col1, col2 = st.columns([1, 1.3])

with col1:
    if "roi" not in st.session_state:
        st.session_state["roi"] = None

    # Initialize interactive map
    m = leafmap.Map(
        center=[19.35, 75.75], zoom=9, draw_control=True, measure_control=True
    )
    m.add_basemap("HYBRID")

    # Display map
    m.to_streamlit(height=600)

    print(m)
    # Draw control GeoJSON data
    drawings = m.user_roi_bounds()  # returns coordinates of drawn ROI (if any)
    if drawings:
        st.session_state["roi"] = drawings
        st.success("✅ ROI captured! Ready for analysis.")
    else:
        st.info("Please draw a polygon ROI on the map before analysis.")

    print(drawings)

    # Year inputs
    year_before = st.number_input("Select BEFORE year", 2000, 2025, 2018)
    year_after = st.number_input("Select AFTER year", 2000, 2025, 2022)

    if st.button("🚀 Analyze Region"):
        if st.session_state["roi"]:
            coords = st.session_state["roi"]
            geojson = {
                "type": "Polygon",
                "coordinates": [coords],
            }

            payload = {
                "geojson": geojson,
                "year_before": year_before,
                "year_after": year_after,
            }

            with st.spinner("Processing on Google Earth Engine (~30s)..."):
                try:
                    resp = requests.post(
                        f"{BACKEND}/analyze", json=payload, timeout=300
                    )
                    if resp.status_code == 200:
                        st.session_state["result"] = resp.json()
                        st.success("✅ Analysis complete!")
                    else:
                        st.error(f"Backend error: {resp.status_code} {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("⚠️ Please draw a region first!")

with col2:
    st.subheader("📊 Results & Visualization")

    if "result" in st.session_state:
        res = st.session_state["result"]
        st.image(res["ndvi_thumb"], caption="NDVI Change Visualization")
        st.write("### NDVI Stats")
        st.json(res["stats"])

        if "NDVI_change" in res["stats"]:
            st.bar_chart({"NDVI Change Mean": [res["stats"]["NDVI_change"]]})
    else:
        st.info("No results yet — draw a region and click Analyze.")
