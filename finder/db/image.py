import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Image(Base):
    __tablename__ = "images"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    collection_id = sa.Column(UUID(as_uuid=True), nullable=True, index=True)

    stored_filename = sa.Column(sa.Text, nullable=False)  # {image.id}.enc
    original_filename = sa.Column(sa.Text, nullable=True)  # {original_name}.{original_extension}
    mime_type = sa.Column(sa.Text, nullable=False)
    size_bytes = sa.Column(sa.BigInteger, nullable=False)

    encryption_metadata = sa.Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    tags = sa.Column(sa.ARRAY(sa.Text), nullable=False, server_default="{}")

    embedding = sa.Column(Vector(512), nullable=False)

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
