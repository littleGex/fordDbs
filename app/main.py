import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.db_manager import db_router
from app.api.v1.pocket_money import pocket_money_router
from app.api.v1.family_photos import family_photos_router
from app.api.v1.utils import utils_router
from app.core.scheduler import start_scheduler
from app.database.database import engine, Base
from app.models.user_models import Child, Transaction  # noqa
from app.models.photo_model import Photo  # noqa
from app.models.utilities import Utils  # noqa
from app.core.storage import init_storage


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up...")

    # 1. Ensure DB tables exist (Wrap in try/except for Docker DB readiness)
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables verified/created.")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        # In a real prod environment, you might want to retry here

    init_storage()
    start_scheduler()
    yield
    print("🛑 Shutting down...")


def create_app():
    app = FastAPI(lifespan=lifespan)

    # --- CORS CONFIGURATION ---
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    # Only split if the string isn't empty, otherwise use a
    # default or empty list
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {
            "message": "Pocket Money API is Live",
            "documentation": "/docs",
            "version": "1.1.0"
        }

    # Create all tables on startup
    Base.metadata.create_all(bind=engine)

    # Plug in our routes
    app.include_router(
        db_router,
        prefix="/v1",
        tags=["Database Management"]
    )

    app.include_router(
        pocket_money_router,
        prefix="/v1/pocket-money",
        tags=["Pocket Money"]
    )

    app.include_router(
        utils_router,
        prefix="/v1/utilities",
        tags=["Utilities"]
    )

    app.include_router(
        family_photos_router,
        prefix="/v1/family-photos",
        tags=["Family Photos"]
    )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
