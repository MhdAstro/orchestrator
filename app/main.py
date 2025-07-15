from fastapi import FastAPI
from api.v1.endpoints import products # <-- پیشوند app حذف شد
app = FastAPI(
    title="Product Orchestrator Service",
    description="Orchestrates product creation by calling multiple external services.",
    version="2.0.0"
)

# Include the product creation router
app.include_router(
    products.router,
    prefix="/api/v1",
    tags=["Product Orchestration"]
)