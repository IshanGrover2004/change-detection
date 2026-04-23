# 🌍 Deforestation & Land Use Change Detector

A full-stack application using **Google Earth Engine (GEE)**, **FastAPI**, and **Streamlit** to detect environmental changes (NDVI) between two years using Sentinel-2 satellite imagery.

## 🚀 Getting Started

### 1. Prerequisites
- A Google Cloud Project with the **Earth Engine API** enabled.
- Python 3.10+ installed.

### 2. Installation

Install dependencies for both the backend and frontend:

```bash
# Install Backend requirements
pip install -r backend_demo/requirements.txt

# Install Frontend requirements
pip install -r frontend/requirements.txt
```

*Note: If you are on a system where pip is restricted (like Ubuntu 23.04+), you may need to use a virtual environment or the `--break-system-packages` flag (not recommended for production).*

### 3. Earth Engine Setup & Authentication

You must authenticate your machine with Google Earth Engine to access satellite data:

```bash
# Install the Earth Engine CLI if not present
pip install earthengine-api

# Run the authentication flow
earthengine authenticate
```
Follow the instructions in your browser to log in with your Google account and copy the verification code back to the terminal.

### 4. Running the Application

You need to run the backend and frontend in separate terminal windows.

#### **Start the Backend (FastAPI)**
```bash
cd backend_demo
uvicorn main:app --reload --port 8000
```
The backend should now be running at `http://localhost:8000`.

#### **Start the Frontend (Streamlit)**
```bash
cd frontend
streamlit run app.py
```
The frontend will open automatically in your browser at `http://localhost:8501`.

## 🛠️ Usage
1. **Select Region:** Use the drawing tools on the interactive map to draw a polygon over your area of interest.
2. **Select Timeline:** Choose the "Before" and "After" years you wish to compare (e.g., 2020 and 2025).
3. **Analyze:** Click **"Run Analysis"**.
4. **Results:** View the NDVI change map (Red = Loss, Green = Gain) and detailed statistics in the results column.

## 🧪 Troubleshooting
- **Black Images:** Ensure your ROI is large enough and that Sentinel-2 imagery exists for the selected years in that region.
- **Connection Error:** Verify that the backend is running on port 8000 before clicking analyze.
- **EE Initialization Failed:** Make sure you have run `earthengine authenticate` and that your GCP project ID is correctly set in `backend_demo/main.py`.
