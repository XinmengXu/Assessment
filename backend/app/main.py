from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import FRONTEND_ORIGINS
from .database import SessionLocal, init_db
from .seed import seed_database


app = FastAPI(title="Explainable Speech-AI Feedback App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in FRONTEND_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
