import ee
import logging
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = "testing-new-477304"

def init_ee():
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception as e:
        logger.error(f"EE Init Error: {e}")

init_ee()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    geojson: dict
    year_before: int
    year_after: int

@app.post("/analyze")
def analyze(req: AnalysisRequest):
    logger.info(f"Processing: {req.year_before} -> {req.year_after}")
    try:
        init_ee()

        # Extract Geometry
        geojson = req.geojson
        if isinstance(geojson, dict) and geojson.get("type") == "Feature":
            geom = ee.Geometry(geojson.get("geometry"))
        elif isinstance(geojson, dict) and geojson.get("type") == "FeatureCollection":
            geom = ee.Geometry(geojson.get("features")[0].get("geometry"))
        else:
            geom = ee.Geometry(geojson)

        def get_indices(year):
            # Using S2_SR_HARMONIZED for consistent values
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geom)
                .filterDate(f"{year}-01-01", f"{year}-12-31")
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                .median()
            )
            
            if collection.bandNames().size().getInfo() == 0:
                raise ValueError(f"No Sentinel-2 imagery available for {year}")
            
            ndvi = collection.normalizedDifference(["B8", "B4"]).rename("NDVI")
            ndwi = collection.normalizedDifference(["B3", "B8"]).rename("NDWI")
            return collection.addBands([ndvi, ndwi]).clip(geom)

        # Generate Indices for both years
        indices1 = get_indices(req.year_before)
        indices2 = get_indices(req.year_after)
        
        # Calculate Change
        ndvi_diff = indices2.select("NDVI").subtract(indices1.select("NDVI")).rename("NDVI_change")
        ndwi_diff = indices2.select("NDWI").subtract(indices1.select("NDWI")).rename("NDWI_change")

        # Get stats
        stats = ndvi_diff.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13
        ).getInfo()
        
        ndwi_stats = ndwi_diff.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13
        ).getInfo()
        
        # Area calculations using thresholds
        # Thresholds:
        # NDVI < -0.15: Significant Vegetation Loss (Deforestation)
        # NDVI > 0.15: Significant Vegetation Gain (Reforestation/Growth)
        # NDWI > 0.1: Significant Water Gain (Flooding/New water)
        # NDWI < -0.1: Significant Water Loss (Drying/Drought)
        
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
        
        stats.update(ndwi_stats)
        stats.update(areas)

        logger.info(f"Calculated Stats with Areas: {stats}")

        # Explicitly define Thumbnail parameters
        ndvi_thumb_params = {
            "region": geom,
            "dimensions": 1024,
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#FF0000", "#FFFFFF", "#00FF00"]
        }
        
        ndwi_thumb_params = {
            "region": geom,
            "dimensions": 1024,
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#A52A2A", "#FFFFFF", "#0000FF"] # Brown, White, Blue
        }
        
        ndvi_url = ndvi_diff.getThumbURL(ndvi_thumb_params)
        ndwi_url = ndwi_diff.getThumbURL(ndwi_thumb_params)
        
        logger.info(f"Generated NDVI URL: {ndvi_url}")
        logger.info(f"Generated NDWI URL: {ndwi_url}")

        return {
            "stats": stats,
            "ndvi_thumb": ndvi_url,
            "ndwi_thumb": ndwi_url,
            "year_before": req.year_before,
            "year_after": req.year_after
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
