from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.db_manager import db_router
from app.api.v1.pocket_money import pocket_money_router
from app.database.database import engine, Base
from app.models.user_models import Child, Transaction  # noqa


load_dotenv()


def create_app():
    app = FastAPI()

    # --- CORS CONFIGURATION ---
    origins = [
        "http://localhost:8080",
        "http://192.168.2.51:8080",
        "http://ford-home-pi.local:8080",
        "http://pocket.local",
    ]

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

    return app


app = create_app()
