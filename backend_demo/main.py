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

        def get_ndvi(year):
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
            return ndvi.clip(geom)

        # Generate NDVI for both years
        ndvi1 = get_ndvi(req.year_before)
        ndvi2 = get_ndvi(req.year_after)
        
        # Calculate Change
        ndvi_diff = ndvi2.subtract(ndvi1).rename("NDVI_change")

        # Get stats
        stats = ndvi_diff.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13
        ).getInfo()

        logger.info(f"Calculated Stats: {stats}")

        # Explicitly define Thumbnail parameters
        # Adding 'region' and 'dimensions' is crucial for correct framing
        thumb_params = {
            "region": geom,
            "dimensions": 1024,  # High res
            "format": "png",
            "min": -0.2, 
            "max": 0.2,
            "palette": ["#FF0000", "#FFFFFF", "#00FF00"] # Direct hex codes for clarity: Red, White, Green
        }
        
        url = ndvi_diff.getThumbURL(thumb_params)
        logger.info(f"Generated URL: {url}")

        return {
            "stats": stats,
            "ndvi_thumb": url,
            "year_before": req.year_before,
            "year_after": req.year_after
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
