import uuid
import sqlalchemy as sa

from finder.db.base import Base


class Collection(Base):
    __tablename__ = "collections"

    id = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    name = sa.Column(sa.String, nullable=False)
    tags = sa.Column(sa.ARRAY(sa.String), nullable=False, server_default=sa.text("'{}'::text[]"))
    is_default = sa.Column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
