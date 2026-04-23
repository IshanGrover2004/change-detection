import streamlit as st
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium
import ee
import json

# --- CONFIGURATION ---
st.set_page_config(page_title="🌳 Deforestation Detector", layout="wide")

# --- EARTH ENGINE AUTHENTICATION ---
def hash_st_secrets(secrets):
    return json.dumps(secrets, sort_keys=True)

@st.cache_resource
def init_ee():
    try:
        # 1. Try to get credentials from Streamlit Secrets (for Deployment)
        if "GEE_JSON" in st.secrets:
            # Parse the JSON secret
            info = json.loads(st.secrets["GEE_JSON"])
            credentials = ee.ServiceAccountCredentials(info['client_email'], key_data=json.dumps(info))
            ee.Initialize(credentials)
            return True, "Authenticated via Service Account"
        
        # 2. Fallback to local user authentication (for Local Dev)
        else:
            ee.Initialize()
            return True, "Authenticated via Local User"
    except Exception as e:
        return False, str(e)

success, msg = init_ee()

# --- ANALYSIS LOGIC ---
def get_ndvi(geom, year):
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        .median()
    )
    
    if collection.bandNames().size().getInfo() == 0:
        return None
        
    ndvi = collection.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return ndvi.clip(geom)

def run_analysis(geojson, year_before, year_after):
    try:
        # Handle Geometry
        if geojson.get("type") == "Feature":
            geom = ee.Geometry(geojson.get("geometry"))
        elif geojson.get("type") == "FeatureCollection":
            geom = ee.Geometry(geojson.get("features")[0].get("geometry"))
        else:
            geom = ee.Geometry(geojson)

        ndvi1 = get_ndvi(geom, year_before)
        ndvi2 = get_ndvi(geom, year_after)
        
        if ndvi1 is None or ndvi2 is None:
            return None, "No imagery found for one of the selected years."

        ndvi_diff = ndvi2.subtract(ndvi1).rename("NDVI_change")

        # Stats
        stats = ndvi_diff.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13
        ).getInfo()

        # Visualization
        thumb_params = {
            "region": geom,
            "dimensions": 1024,
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#FF0000", "#FFFFFF", "#00FF00"]
        }
        url = ndvi_diff.getThumbURL(thumb_params)
        
        return {"stats": stats, "url": url}, None
    except Exception as e:
        return None, str(e)

# --- UI LAYOUT ---
st.title("🌍 Standalone Deforestation Detector")
if not success:
    st.error(f"❌ Earth Engine failed to initialize: {msg}")
    st.info("If deploying to Streamlit Cloud, add your Service Account JSON to 'Secrets' as GEE_JSON.")
    st.stop()

col1, col2 = st.columns([1, 1.2])

with col1:
    if "roi" not in st.session_state:
        st.session_state["roi"] = None

    st.subheader("🗺️ 1. Select Region")
    m = leafmap.Map(center=[19.35, 75.75], zoom=9, draw_control=True)
    m.add_basemap("HYBRID")

    output = st_folium(m, height=450, width=None, key="map_deploy", returned_objects=["last_draw", "all_drawings"])

    if output:
        draw = output.get("last_draw")
        if draw and draw.get("geometry"):
            st.session_state["roi"] = draw["geometry"]
        elif output.get("all_drawings"):
            st.session_state["roi"] = output["all_drawings"][-1]["geometry"]

    if st.session_state.get("roi"):
        st.success("✅ ROI captured.")
    else:
        st.info("👆 Draw a shape on the map.")

    st.markdown("---")
    st.subheader("📅 2. Select Timeline")
    y_before = st.number_input("Before Year", 2000, 2026, 2020)
    y_after = st.number_input("After Year", 2000, 2026, 2025)

    if st.button("🚀 Run Analysis", type="primary"):
        if not st.session_state.get("roi"):
            st.warning("Please draw a region first!")
        else:
            with st.spinner("Analyzing satellite data..."):
                result, err = run_analysis(st.session_state["roi"], y_before, y_after)
                if err:
                    st.error(err)
                else:
                    st.session_state["deploy_result"] = result

with col2:
    st.subheader("📊 3. Analysis Results")
    if "deploy_result" in st.session_state:
        res = st.session_state["deploy_result"]
        st.image(res["url"], caption="Red: Loss | Green: Gain", use_container_width=True)
        
        stats = res.get("stats", {})
        mean_change = stats.get("NDVI_change", 0)
        st.metric("Mean NDVI Change", f"{mean_change:.4f}")
        st.json(stats)
    else:
        st.info("Results will appear here.")
