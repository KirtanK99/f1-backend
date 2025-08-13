from sqlalchemy import Column, Integer, String, Date, ForeignKey, UniqueConstraint, Float, Index
from sqlalchemy.orm import relationship
from app.db.base import Base


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    country = Column(String, nullable=True)
    drivers = relationship("Driver", back_populates="team")

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    nationality = Column(String, nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    team = relationship("Team", back_populates="drivers")

class Race(Base):
    __tablename__ = "races"
    __table_args__ = (UniqueConstraint("year", "round", name="unique_races_year_round"),)
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    country = Column(String, nullable=True)
    location = Column(String, nullable=True)
    year = Column(Integer, nullable=False)
    round = Column(Integer, nullable=False)
    grand_prix = Column(String, nullable=False)
    circuit = Column(String, nullable=True)
    date = Column(Date, nullable=True)

class RaceResult(Base):
    __tablename__ = "race_results"
    __table_args__ = (
        UniqueConstraint("race_id", "driver_id", name="unique_race_driver"),
        Index("ix_race_results_race_pos", "race_id", "position"),
    )
    id = Column(Integer, primary_key=True, index=True)
    race_id = Column(Integer, ForeignKey("races.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)

    # Core fields (nullable=True because some sessions lack data)
    position = Column(Integer, nullable=True)      # 1..20, or None (DNF/DSQ/no result)
    grid = Column(Integer, nullable=True)          # starting grid position
    status = Column(String, nullable=True)         # e.g., "Finished", "DNF"
    time_ms = Column(Integer, nullable=True)       # race time in milliseconds
    points = Column(Float, nullable=True)          # points scored

    # Optional relationships (handy later)
    race = relationship("Race")
    driver = relationship("Driver")
