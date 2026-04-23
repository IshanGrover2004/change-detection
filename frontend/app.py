import json
import requests
import streamlit as st
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium

st.set_page_config(page_title="🌳 Deforestation Detector", layout="wide")

BACKEND = "http://127.0.0.1:8000"

st.title("🌍 Land Use & Deforestation Change Detection")

# Sidebar for configuration and debugging
with st.sidebar:
    st.header("⚙️ Settings")
    debug_mode = st.checkbox("Show Raw Map Data", value=False)
    
    if st.button("🔌 Test Backend Connection"):
        try:
            r = requests.get(f"{BACKEND}/", timeout=5)
            st.success(f"Connected! Status: {r.json()}")
        except Exception as e:
            st.error(f"Failed: {e}")

    st.markdown("---")
    st.markdown("### 🛠️ Fallback Tools")
    if st.button("📍 Use Default ROI (Aurangabad)"):
        st.session_state["roi"] = {
            "type": "Polygon",
            "coordinates": [[[75.2, 19.8], [75.5, 19.8], [75.5, 19.6], [75.2, 19.6], [75.2, 19.8]]]
        }
        st.success("Loaded default region!")

col1, col2 = st.columns([1, 1.2])

with col1:
    if "roi" not in st.session_state:
        st.session_state["roi"] = None

    st.subheader("🗺️ 1. Select Region")
    # Initialize map
    m = leafmap.Map(center=[19.35, 75.75], zoom=9, draw_control=True)
    m.add_basemap("HYBRID")

    # Use st_folium directly for better event handling
    output = st_folium(m, height=450, width=None, key="map_v3", returned_objects=["last_draw", "all_drawings"])

    # Update ROI if drawing is detected
    if output:
        draw = output.get("last_draw")
        if draw and draw.get("geometry"):
            st.session_state["roi"] = draw["geometry"]
        elif output.get("all_drawings"):
            st.session_state["roi"] = output["all_drawings"][-1]["geometry"]

    if debug_mode:
        with st.expander("Raw Map Output"):
            st.write(output)

    # Current Status
    if st.session_state.get("roi"):
        st.success("✅ ROI captured and ready.")
        if st.button("🗑️ Clear ROI"):
            st.session_state["roi"] = None
            st.rerun()
    else:
        st.info("👆 Draw a shape on the map to select an area.")

    st.markdown("---")
    st.subheader("📅 2. Select Timeline")
    # Parameters
    year_before = st.number_input("Before Year", 2000, 2026, 2020)
    year_after = st.number_input("After Year", 2000, 2026, 2025)

    if st.button("🚀 Run Analysis", type="primary"):
        if not st.session_state.get("roi"):
            st.warning("Please draw a region first!")
        else:
            payload = {
                "geojson": st.session_state["roi"],
                "year_before": year_before,
                "year_after": year_after,
            }
            
            with st.spinner("Requesting Earth Engine analysis..."):
                try:
                    res = requests.post(f"{BACKEND}/analyze", json=payload, timeout=300)
                    if res.status_code == 200:
                        st.session_state["result"] = res.json()
                    else:
                        st.error(f"Backend Error: {res.text}")
                except Exception as e:
                    st.error(f"Connection Error: {e}")

with col2:
    st.subheader("📊 3. Analysis Results")
    
    if "result" in st.session_state:
        res = st.session_state["result"]
        
        # Main Result Image
        if "ndvi_thumb" in res:
            st.markdown("#### Vegetation Change Map")
            st.image(res["ndvi_thumb"], 
                     caption="Red: Forest Loss | White: No Change | Green: Forest Gain", 
                     use_container_width=True)
        
        # Metrics Row
        stats = res.get("stats", {})
        if stats:
            st.markdown("---")
            mean_change = stats.get("NDVI_change", 0)
            
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Mean NDVI Change", f"{mean_change:.4f}", 
                          delta="Gain" if mean_change > 0 else "Loss", 
                          delta_color="normal" if mean_change > 0 else "inverse")
            
            with m2:
                status = "Healthy Growth" if mean_change > 0.05 else "Potential Deforestation" if mean_change < -0.05 else "Stable"
                st.write(f"**Region Status:** {status}")

            with st.expander("View Detailed Statistics"):
                st.json(stats)
        
        if st.button("🔄 Start New Analysis"):
            if "result" in st.session_state:
                del st.session_state["result"]
            st.rerun()
            
    else:
        st.info("Analysis results (NDVI change maps and statistics) will be displayed here once you click 'Run Analysis'.")
