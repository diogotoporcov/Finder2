import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from finder.db.base import Base


class ImageFingerprint(Base):
    __tablename__ = "image_fingerprints"

    image_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("images.id", ondelete="CASCADE"),
        primary_key=True,
    )

    sha256 = sa.Column(sa.String(64), index=True, nullable=False)
    phash = sa.Column(sa.BigInteger, index=True, nullable=False)
    embedding = sa.Column(Vector(512), nullable=False)

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
