import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.db_manager import db_router
from app.api.v1.pocket_money import pocket_money_router
from app.api.v1.family_photos import family_photos_router
from app.core.scheduler import start_scheduler
from app.database.database import engine, Base
from app.models.user_models import Child, Transaction  # noqa
from app.models.photo_model import Photo  # noqa
from app.core.storage import init_storage


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print("🚀 Starting up...")
    init_storage()
    start_scheduler()
    yield
    # --- Shutdown Logic (Optional) ---
    print("🛑 Shutting down...")


def create_app():
    app = FastAPI(lifespan=lifespan)

    # --- CORS CONFIGURATION ---
    origins = os.getenv("ALLOWED_ORIGINS",
                        "").split(",")

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
    app.include_router(db_router,
                       prefix="/v1",
                       tags=["Database Management"])
    app.include_router(pocket_money_router,
                       prefix="/v1/pocket-money",
                       tags=["Pocket Money"])

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
