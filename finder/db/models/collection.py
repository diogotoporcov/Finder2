import uuid
import sqlalchemy as sa
from sqlalchemy import event, Connection, select
from sqlalchemy.orm import Mapper, Session

from finder.db.base import Base


class Collection(Base):
    __tablename__ = "collections"

    id = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    name = sa.Column(sa.String(64), nullable=False)
    tags = sa.Column(sa.ARRAY(sa.String(64)), nullable=False, server_default=sa.text("'{}'::text[]"))
    is_default = sa.Column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


class DefaultCollectionDeletion(Exception):
    pass


class DefaultCollectionCreation(Exception):
    pass


class DefaultCollectionRename(Exception):
    pass


@event.listens_for(Collection, "before_delete")
def prevent_default_collection_delete(_mapper: Mapper, _connection: Connection, target: Collection):
    if target.is_default:
        raise DefaultCollectionDeletion("Cannot delete the default collection.")


@event.listens_for(Collection, "before_insert")
def prevent_multiple_default_collections(_mapper: Mapper, connection: Connection, target: Collection):
    if not target.is_default:
        return

    with Session(bind=connection) as session:
        exists = session.execute(
            select(Collection.id).where(
                Collection.owner_id == target.owner_id,
                Collection.is_default.is_(True)
            )
        ).first()
        if exists:
            raise DefaultCollectionCreation("User already has a default collection.")


@event.listens_for(Collection, "before_update")
def prevent_rename_or_update_default(_mapper: Mapper, _connection: Connection, target: Collection):
    if hasattr(target, "is_default") and target.is_default:
        raise DefaultCollectionRename("Cannot update a collection to is_default=True.")
