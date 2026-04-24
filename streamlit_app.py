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
def get_indices(geom, year):
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
    ndwi = collection.normalizedDifference(["B3", "B8"]).rename("NDWI")
    return collection.addBands([ndvi, ndwi]).clip(geom)

def run_analysis(geojson, year_before, year_after):
    try:
        # Handle Geometry
        if geojson.get("type") == "Feature":
            geom = ee.Geometry(geojson.get("geometry"))
        elif geojson.get("type") == "FeatureCollection":
            geom = ee.Geometry(geojson.get("features")[0].get("geometry"))
        else:
            geom = ee.Geometry(geojson)

        indices1 = get_indices(geom, year_before)
        indices2 = get_indices(geom, year_after)
        
        if indices1 is None or indices2 is None:
            return None, "No imagery found for one of the selected years."

        ndvi_diff = indices2.select("NDVI").subtract(indices1.select("NDVI")).rename("NDVI_change")
        ndwi_diff = indices2.select("NDWI").subtract(indices1.select("NDWI")).rename("NDWI_change")

        # Stats
        stats = ndvi_diff.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13
        ).getInfo()
        
        # Area calculations using thresholds
        pixelArea = ee.Image.pixelArea()
        
        veg_loss_mask = ndvi_diff.lt(-0.15)
        veg_gain_mask = ndvi_diff.gt(0.15)
        water_gain_mask = ndwi_diff.gt(0.1)
        water_loss_mask = ndwi_diff.lt(-0.1)
        
        def get_area_km2(mask):
            area_m2 = pixelArea.updateMask(mask).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geom,
                scale=30,
                maxPixels=1e13
            ).getInfo().get("area", 0)
            return (area_m2 or 0) / 1e6

        areas = {
            "veg_loss_km2": get_area_km2(veg_loss_mask),
            "veg_gain_km2": get_area_km2(veg_gain_mask),
            "water_gain_km2": get_area_km2(water_gain_mask),
            "water_loss_km2": get_area_km2(water_loss_mask)
        }
        
        stats.update(areas)

        # Visualization
        thumb_params_ndvi = {
            "region": geom,
            "dimensions": 1024,
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#FF0000", "#FFFFFF", "#00FF00"]
        }
        
        thumb_params_ndwi = {
            "region": geom,
            "dimensions": 1024,
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#A52A2A", "#FFFFFF", "#0000FF"]
        }
        
        ndvi_url = ndvi_diff.getThumbURL(thumb_params_ndvi)
        ndwi_url = ndwi_diff.getThumbURL(thumb_params_ndwi)
        
        return {
            "stats": stats, 
            "ndvi_url": ndvi_url,
            "ndwi_url": ndwi_url
        }, None
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
        stats = res.get("stats", {})
        
        st.markdown("#### 🌿 Vegetation Change (NDVI)")
        st.image(res["ndvi_url"], caption="Red: Loss | White: No Change | Green: Gain", width="stretch")
        
        st.markdown("#### 💧 Water/Moisture Change (NDWI)")
        st.image(res["ndwi_url"], caption="Brown: Loss | White: No Change | Blue: Gain", width="stretch")
        
        # Human-Friendly Insights Section
        st.markdown("---")
        st.subheader("💡 Key Environmental Insights")
        
        m1, m2 = st.columns(2)
        
        with m1:
            st.markdown("#### 🌳 Vegetation Impact")
            loss = stats.get("veg_loss_km2", 0)
            gain = stats.get("veg_gain_km2", 0)
            
            if loss > 0.01:
                st.warning(f"**Significant Forest Loss:** ~{loss:.2f} km²")
            if gain > 0.01:
                st.success(f"**Significant Growth:** ~{gain:.2f} km²")
            if loss <= 0.01 and gain <= 0.01:
                st.info("Vegetation levels remained stable.")

        with m2:
            st.markdown("#### 💧 Water & Moisture")
            w_gain = stats.get("water_gain_km2", 0)
            w_loss = stats.get("water_loss_km2", 0)
            
            if w_gain > 0.01:
                st.info(f"**Water Increase:** ~{w_gain:.2f} km²")
            if w_loss > 0.01:
                st.error(f"**Drying/Water Loss:** ~{w_loss:.2f} km²")
            if w_gain <= 0.01 and w_loss <= 0.01:
                st.info("Water/Moisture levels stable.")

        st.markdown("---")
        st.subheader("📈 Detailed Index Metrics")
        
        mean_ndvi = stats.get("NDVI_change", 0)
        mean_ndwi = stats.get("NDWI_change", 0)
        
        m1, m2 = st.columns(2)
        m1.metric("Mean NDVI Change", f"{mean_ndvi:.4f}")
        m2.metric("Mean NDWI Change", f"{mean_ndwi:.4f}")
        
        with st.expander("Detailed Stats"):
            st.json(stats)
    else:
        st.info("Results will appear here.")

    st.markdown("---")
