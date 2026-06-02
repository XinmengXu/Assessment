from app.database import SessionLocal, init_db
from app.seed import seed_database


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
        print("Seed data created.")
    finally:
        db.close()
