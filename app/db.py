from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

def make_engine(db_url: str):
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )

def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
