import sqlalchemy as sa
from finder.db.base import Base


class ImageDuplicate(Base):
    __tablename__ = "image_duplicates"

    image_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("images.id", ondelete="CASCADE"),
        primary_key=True,
    )

    original_image_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("images.id", ondelete="CASCADE"),
    )

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
