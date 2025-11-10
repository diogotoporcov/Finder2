import uuid
from sqlalchemy import Column, String, DateTime, func, event, Connection
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapper
import sqlalchemy as sa

from src.db.base import Base
from src.db.models.collection import Collection


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(128), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


@event.listens_for(User, "after_insert")
def create_default_collection(_mapper: Mapper, connection: Connection, target: User) -> None:
    """
    Create the default collection for a new user.
    """
    connection.execute(
        sa.insert(Collection).values(
            owner_id=target.id,
            name="DEFAULT",
            is_default=True,
        )
    )