from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import (Table, Column, String, Integer,
                        MetaData, inspect, Boolean, Float,
                        text, DateTime)
from sqlalchemy.schema import CreateTable
from app.database.database import get_db, engine


db_router = APIRouter()
metadata = MetaData()
type_map = {
    "string": String,
    "integer": Integer,
    "boolean": Boolean,
    "float": Float,
    "datetime": DateTime
}


@db_router.get("/list-tables")
def get_tables(db: Session = Depends(get_db)):
    # Logic to fetch all table names in the current DB
    query = text("SELECT tablename FROM pg_catalog.pg_tables"
                 " WHERE schemaname='public'")
    result = db.execute(query)
    return {"tables": [row[0] for row in result]}


@db_router.post("/create-table/{table_name}")
def create_custom_table(table_name: str, columns: dict[str, str]):
    """
    Endpoint to create a new table.
    Body example: {"age": "integer", "bio": "string", "is_active": "boolean"}
    """
    inspector = inspect(engine)

    # 1. Safety check: Does table exist?
    if table_name in inspector.get_table_names():
        raise HTTPException(status_code=400, detail="Table already exists")

    try:
        # 2. Define the structure
        new_table = Table(
            table_name,
            metadata,
            Column('id',
                   Integer,
                   primary_key=True,
                   autoincrement=True)
        )

        for col_name, col_type in columns.items():
            sa_type = type_map.get(col_type.lower(), String)
            new_table.append_column(Column(col_name, sa_type))

        # 3. Execute the DDL using the Engine
        with engine.begin() as conn:
            conn.execute(CreateTable(new_table))

        return {"message": f"Table '{table_name}' created successfully",
                "columns": list(columns.keys())}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@db_router.post("/tables/{table_name}/records")
def add_record(table_name: str, data: dict):
    # "Autoload" tells SQLAlchemy to go ask the DB what this table looks like
    table = Table(table_name, metadata, autoload_with=engine)

    with engine.begin() as conn:
        conn.execute(table.insert().values(**data))

    return {"status": "Record added"}


@db_router.get("/tables/{table_name}")
def get_table_data(table_name: str):
    try:
        # Use a fresh MetaData object for each dynamic reflection
        local_metadata = MetaData()
        table = Table(table_name, local_metadata, autoload_with=engine)

        with engine.connect() as conn:
            result = conn.execute(table.select())
            # mappings().all() is the cleanest way to return a list of dicts
            return {"data": result.mappings().all()}
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' not found.")
