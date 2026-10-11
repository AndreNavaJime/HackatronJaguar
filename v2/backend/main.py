"""PantheraID v2 API foundation. Run: uvicorn main:app --reload (from v2/backend)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PantheraID API", version="0.1.0")
# Configure production origins before deployment. Local development only.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PantheraID API", "version": "0.1.0"}

@app.get("/api/capabilities")
def capabilities():
    return {
        "modules": ["PantheraID", "PantheraMONITORING", "PantheraEDGE"],
        "image_analysis": "not_migrated",
        "video_analysis": "not_migrated",
        "supabase": "not_configured",
        "edge_ingestion": "not_migrated",
    }
