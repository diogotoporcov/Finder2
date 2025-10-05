import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from finder.db.base import Base


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    owner_id = sa.Column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    expires_at = sa.Column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5*60),
        nullable=False
    )


class UploadSessionImage(Base):
    __tablename__ = "upload_session_images"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    upload_session_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("upload_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    image_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("images.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    created_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    )
