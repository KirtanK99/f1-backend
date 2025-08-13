try:
    # SQLAlchemy 2.x
    from sqlalchemy.orm import DeclarativeBase
    class Base(DeclarativeBase):
        pass
except Exception:
    # Fallback for SQLAlchemy 1.4
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
