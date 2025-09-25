import uuid
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Image(Base):
    __tablename__ = "images"

    id = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    collection_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    stored_filename = sa.Column(sa.String(40), nullable=False)  # {image.id}.enc
    original_filename = sa.Column(sa.String(256), nullable=True)  # {original_name}.{ext}
    mime_type = sa.Column(sa.String(100), nullable=False)  # e.g. "image/png"
    size_bytes = sa.Column(sa.BigInteger, nullable=False)

    encryption_metadata = sa.Column(sa.JSON, nullable=False, server_default=sa.text("'{}'::jsonb"))

    tags = sa.Column(sa.ARRAY(sa.String), nullable=False, server_default="{}")

    embedding = sa.Column(Vector(512), nullable=False)

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
