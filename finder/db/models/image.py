import uuid
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from finder.db.base import Base


class Image(Base):
    __tablename__ = "images"

    id = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    owner_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    collection_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    stored_filename = sa.Column(sa.String(256), nullable=False)
    original_filename = sa.Column(sa.String(256), nullable=False)
    mime_type = sa.Column(sa.String(100), nullable=False)
    size_bytes = sa.Column(sa.BigInteger, nullable=False)

    tags = sa.Column(sa.ARRAY(sa.String), nullable=False, server_default="{}")

    sha256 = sa.Column(sa.String(64), index=True, nullable=False)
    phash = sa.Column(sa.BigInteger, index=True, nullable=False)
    embedding = sa.Column(Vector(512), nullable=True)

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
