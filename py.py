import ee

# Initialize Earth Engine with your project
ee.Initialize(project="testing-new-477304")
print("Projet initialization done")

# Test a small image load
image = ee.Image("COPERNICUS/S2_SR/20210101T043539_20210101T044522_T44PDT")
print("Bands:", image.bandNames().getInfo())

print("✅ Earth Engine connected successfully!")
