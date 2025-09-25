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

    temp_path = sa.Column(sa.Text, nullable=False)
    original_filename = sa.Column(sa.Text, nullable=True)
    mime_type = sa.Column(sa.Text, nullable=False)
    size_bytes = sa.Column(sa.BigInteger, nullable=False)
    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)