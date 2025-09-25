import datetime
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    temp_name = sa.Column(sa.Text, nullable=False)
    original_filename = sa.Column(sa.String(256), nullable=True)  # {original_name}.{ext}
    mime_type = sa.Column(sa.String(100), nullable=False)  # e.g. "image/png"
    size_bytes = sa.Column(sa.BigInteger, nullable=False)

    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    expires_at = sa.Column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5*60),
        nullable=False
    )
