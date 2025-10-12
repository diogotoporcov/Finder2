import uuid, sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from finder.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    jti_hash = sa.Column(sa.String(64), nullable=False, unique=True, index=True)
    revoked = sa.Column(sa.Boolean, nullable=False, server_default=sa.text("false"))

    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    created_at = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
