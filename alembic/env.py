import os  # Add this
from dotenv import load_dotenv  # Add this
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.database.database import Base
from app.models.user_models import User, Child, Transaction, Wish # noqa
from app.models.photo_model import Photo, Like, Comment, View    # noqa


load_dotenv()  # Load your variables from .env


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Helper function to build the URL dynamically
def get_url():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    server = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "postgres_db")
    return f"postgresql+psycopg2://{user}:{password}@{server}:{port}/{db}"


def run_migrations_offline():
    # Replace 'url = config.get_main_option("sqlalchemy.url")' with:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Replace the existing connectable logic with this:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()  # This overrides the .ini file

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()
