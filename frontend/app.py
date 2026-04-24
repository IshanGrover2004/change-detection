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
        stats = res.get("stats", {})
        
        # Main Result Images
        ndvi_key = "ndvi_thumb" if "ndvi_thumb" in res else "ndvi_change_thumb"
        ndwi_key = "ndwi_thumb" if "ndwi_thumb" in res else "ndwi_change_thumb"

        if ndvi_key in res:
            st.markdown("#### 🌿 Vegetation Change (NDVI)")
            st.image(res[ndvi_key], 
                     caption="Red: Loss | White: No Change | Green: Gain", 
                     width="stretch")
        
        if ndwi_key in res:
            st.markdown("#### 💧 Water/Moisture Change (NDWI)")
            st.image(res[ndwi_key], 
                     caption="Brown: Loss | White: No Change | Blue: Gain", 
                     width="stretch")
        
        # Human-Friendly Insights Section
        st.markdown("---")
        st.subheader("💡 Key Environmental Insights")
        
        m1, m2 = st.columns(2)
        
        with m1:
            st.markdown("#### 🌳 Vegetation Impact")
            loss = stats.get("veg_loss_km2", 0) or stats.get("deforestation_km2", 0)
            gain = stats.get("veg_gain_km2", 0)
            
            if loss > 0.01:
                st.warning(f"**Significant Forest Loss:** ~{loss:.2f} km² of vegetation has disappeared.")
            if gain > 0.01:
                st.success(f"**Significant Growth:** ~{gain:.2f} km² of new vegetation detected.")
            if loss <= 0.01 and gain <= 0.01:
                st.info("Vegetation levels remained relatively stable.")

        with m2:
            st.markdown("#### 💧 Water & Moisture")
            w_gain = stats.get("water_gain_km2", 0)
            w_loss = stats.get("water_loss_km2", 0)
            
            if w_gain > 0.01:
                st.info(f"**Water Increase:** ~{w_gain:.2f} km² of new surface water or high moisture detected.")
            if w_loss > 0.01:
                st.error(f"**Drying/Water Loss:** ~{w_loss:.2f} km² of water or moisture has been lost.")
            if w_gain <= 0.01 and w_loss <= 0.01:
                st.info("Water/Moisture levels remained relatively stable.")
        
        # Original metrics section follows
        st.markdown("---")
        st.subheader("📈 Detailed Index Metrics")
        m1, m2 = st.columns(2)

        # Case 1: Mean Change Stats (from main.py)
        if "NDVI_change" in stats or "NDWI_change" in stats:
            mean_ndvi_change = stats.get("NDVI_change", 0)
            mean_ndwi_change = stats.get("NDWI_change", 0)

            with m1:
                st.metric("Mean NDVI Change", f"{mean_ndvi_change:.4f}", 
                          delta="Gain" if mean_ndvi_change > 0 else "Loss", 
                          delta_color="normal" if mean_ndvi_change > 0 else "inverse")

            with m2:
                st.metric("Mean NDWI Change", f"{mean_ndwi_change:.4f}", 
                          delta="Gain" if mean_ndwi_change > 0 else "Loss", 
                          delta_color="normal" if mean_ndwi_change > 0 else "inverse")

        # Case 2: Area Stats (from app.py)
        elif "deforestation_km2" in stats or "water_gain_km2" in stats:
            def_km2 = stats.get("deforestation_km2", 0)
            water_km2 = stats.get("water_gain_km2", 0)

            with m1:
                st.metric("Deforestation Area", f"{def_km2:.2f} km²", 
                          delta=f"{stats.get('deforestation_m2', 0):.0f} m²",
                          delta_color="inverse")

            with m2:
                st.metric("Water Gain Area", f"{water_km2:.2f} km²", 
                          delta=f"{stats.get('water_gain_m2', 0):.0f} m²",
                          delta_color="normal")

        # Status summary based on NDVI if available
        if "NDVI_change" in stats:
            mean_change = stats["NDVI_change"]
            status = "Healthy Growth" if mean_change > 0.05 else "Potential Deforestation" if mean_change < -0.05 else "Stable"
            st.write(f"**Region Vegetation Status:** {status}")
            with st.expander("View Detailed Statistics"):
                st.json(stats)
        
        if st.button("🔄 Start New Analysis"):
            if "result" in st.session_state:
                del st.session_state["result"]
            st.rerun()
            
    else:
        st.info("Analysis results (NDVI change maps and statistics) will be displayed here once you click 'Run Analysis'.")
