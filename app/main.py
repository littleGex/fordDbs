from dotenv import load_dotenv
from fastapi import FastAPI
from app.api.v1.db_manager import db_router
from app.database.database import engine, Base


load_dotenv()


def create_app():
    app = FastAPI()

    # Create all tables on startup
    Base.metadata.create_all(bind=engine)

    # Plug in our routes
    app.include_router(db_router,
                       prefix="/v1",
                       tags=["Database Management"])

    return app

app = create_app()
