# backend/app.py
import json
import os
from typing import Any, Dict

import ee
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shapely.geometry import mapping, shape

# Initialize Earth Engine
# For interactive local use: ensure you have run `earthengine authenticate`
try:
    ee.Initialize()
except Exception as e:
    # If ee.Initialize fails, raise a helpful error later
    print("Warning: ee.Initialize() failed. Authenticate Earth Engine first.", str(e))

app = FastAPI(title="Change Detection GEE API")

# Allow CORS for local dev (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ROIRequest(BaseModel):
    geojson: Dict[str, Any]
    year_before: int = 2018
    year_after: int = 2022
    ndvi_threshold: float = -0.15  # for deforestation detection


def to_ee_geometry(geojson):
    # Convert a GeoJSON geometry to ee.Geometry
    return ee.Geometry(geojson)


def make_sentinel_composite(roi_ee, start, end, cloud_mask=True):
    col = (
        ee.ImageCollection("COPERNICUS/S2").filterBounds(roi_ee).filterDate(start, end)
    )
    if cloud_mask:

        def maskClouds(image):
            qa = image.select("QA60")
            cloudBit = 1 << 10
            cirrusBit = 1 << 11
            mask = qa.bitwiseAnd(cloudBit).eq(0).And(qa.bitwiseAnd(cirrusBit).eq(0))
            return image.updateMask(mask)

        col = col.map(maskClouds)
    # select needed bands
    col = col.select(["B4", "B3", "B2", "B8", "B11"])
    comp = col.median().clip(roi_ee)
    return comp


def add_indices(img):
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = img.normalizedDifference(["B3", "B11"]).rename("NDWI")
    return img.addBands([ndvi, ndwi])


def get_thumb_url(image, vis_params, region, scale=30, width=1024, height=1024):
    # Use getThumbURL for quick visualization
    params = {
        "region": (
            region.toGeoJSONString()
            if hasattr(region, "toGeoJSONString")
            else json.dumps(region)
        ),
        "dimensions": width,
        "min": vis_params.get("min"),
        "max": vis_params.get("max"),
        "palette": ",".join(vis_params.get("palette", [])),
    }
    return image.getThumbURL(params)


@app.post("/analyze")
def analyze(req: ROIRequest):
    try:
        geojson = req.geojson
        # Convert to ee.Geometry
        if "type" in geojson and geojson["type"] == "Feature":
            geometry = geojson["geometry"]
        elif "type" in geojson and geojson["type"] == "FeatureCollection":
            geometry = geojson["features"][0]["geometry"]
        elif "type" in geojson and geojson["type"] in ("Polygon", "MultiPolygon"):
            geometry = geojson
        else:
            # assume geometry directly
            geometry = geojson

        roi_ee = ee.Geometry(geometry)

        # Build composites
        start1 = f"{req.year_before}-01-01"
        end1 = f"{req.year_before}-12-31"
        start2 = f"{req.year_after}-01-01"
        end2 = f"{req.year_after}-12-31"

        comp1 = make_sentinel_composite(roi_ee, start1, end1)
        comp2 = make_sentinel_composite(roi_ee, start2, end2)

        i1 = add_indices(comp1)
        i2 = add_indices(comp2)

        ndvi1 = i1.select("NDVI")
        ndvi2 = i2.select("NDVI")
        ndwi1 = i1.select("NDWI")
        ndwi2 = i2.select("NDWI")

        ndvi_change = ndvi2.subtract(ndvi1).rename("NDVI_change")
        ndwi_change = ndwi2.subtract(ndwi1).rename("NDWI_change")

        # quick visualization thumbnails (use palettes)
        ndvi_vis = {"min": -0.6, "max": 0.6, "palette": ["red", "white", "green"]}
        ndwi_vis = {"min": -0.6, "max": 0.6, "palette": ["brown", "white", "blue"]}

        # Create thumbnails (these are URLs that encode the image)
        ndvi_url = get_thumb_url(
            ndvi_change.visualize(
                **{"min": -0.6, "max": 0.6, "palette": ["red", "white", "green"]}
            ),
            ndvi_vis,
            geometry,
        )
        ndwi_url = get_thumb_url(
            ndwi_change.visualize(
                **{"min": -0.6, "max": 0.6, "palette": ["brown", "white", "blue"]}
            ),
            ndwi_vis,
            geometry,
        )

        # Area calculations (in m2)
        pixelArea = ee.Image.pixelArea()
        def_mask = ndvi_change.lt(req.ndvi_threshold)
        water_gain_mask = ndwi_change.gt(0.12)

        def_area_m2 = (
            pixelArea.updateMask(def_mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=roi_ee, scale=30, maxPixels=1e13
            )
            .getInfo()
        )

        water_area_m2 = (
            pixelArea.updateMask(water_gain_mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=roi_ee, scale=30, maxPixels=1e13
            )
            .getInfo()
        )

        def_area_val = (
            def_area_m2.get("area", 0) if isinstance(def_area_m2, dict) else 0
        )
        water_area_val = (
            water_area_m2.get("area", 0) if isinstance(water_area_m2, dict) else 0
        )

        # Vectorize deforestation mask to GeoJSON (limit size)
        vectors = def_mask.selfMask().reduceToVectors(
            {
                "geometry": roi_ee,
                "geometryType": "polygon",
                "scale": 30,
                "maxPixels": 1e13,
            }
        )

        vectors_geojson = vectors.getInfo()  # may be large; fine for moderate ROI sizes

        # NDVI histogram (sample)
        ndvi_hist = ndvi_change.reduceRegion(
            reducer=ee.Reducer.histogram(), geometry=roi_ee, scale=30, maxPixels=1e13
        ).getInfo()

        response = {
            "ndvi_change_thumb": ndvi_url,
            "ndwi_change_thumb": ndwi_url,
            "deforestation_geojson": vectors_geojson,
            "stats": {
                "deforestation_m2": def_area_val,
                "deforestation_km2": def_area_val / 1e6 if def_area_val else 0,
                "water_gain_m2": water_area_val,
                "water_gain_km2": water_area_val / 1e6 if water_area_val else 0,
            },
            "ndvi_histogram": (
                ndvi_hist.get("NDVI_change") if isinstance(ndvi_hist, dict) else {}
            ),
        }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
