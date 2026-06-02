from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .database import SessionLocal, init_db
from .seed import seed_database


app = FastAPI(title="Explainable Speech-AI Feedback App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
