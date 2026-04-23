import ee
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ✅ Initialize Earth Engine (replace with your GCP project ID)
ee.Initialize(project="testing-new-477304")

app = FastAPI(title="Deforestation Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    geojson: dict
    year_before: int
    year_after: int


@app.get("/")
def home():
    return {"message": "Backend running successfully!"}


@app.post("/analyze")
def analyze(req: AnalysisRequest):
    geom = ee.Geometry(req.geojson)

    def get_ndvi(year):
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterDate(f"{year}-01-01", f"{year}-12-31")
            .filterBounds(geom)
            .median()
        )
        ndvi = collection.normalizedDifference(["B8", "B4"]).rename("NDVI")
        return ndvi.clip(geom)

    ndvi_before = get_ndvi(req.year_before)
    ndvi_after = get_ndvi(req.year_after)

    ndvi_diff = ndvi_after.subtract(ndvi_before).rename("NDVI_change")

    stats = ndvi_diff.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=30,
        maxPixels=1e13,
    ).getInfo()

    ndvi_vis = {"min": -0.5, "max": 0.5, "palette": ["red", "white", "green"]}
    url = ndvi_diff.getThumbURL(ndvi_vis)

    return {
        "stats": stats,
        "ndvi_thumb": url,
        "year_before": req.year_before,
        "year_after": req.year_after,
    }
