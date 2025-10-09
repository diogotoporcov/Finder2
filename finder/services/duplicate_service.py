import uuid

import sqlalchemy as sa
import sqlalchemy.dialects
from sqlalchemy.orm import Session

from finder.db.models.image import Image


class DuplicateService:
    PHASH_THRESHOLD = 5

    @classmethod
    def detect_duplicate(
        cls,
        db: Session,
        owner_id: uuid.UUID,
        collection_id: uuid.UUID,
        sha256: str,
        phash: bytes,
    ) -> bool:
        existing = db.query(Image).filter(
            Image.owner_id == owner_id,
            Image.sha256 == sha256
        ).first()
        if existing:
            return True

        phash_int = int.from_bytes(phash, "big", signed=True)

        candidate = (
            db.query(Image)
            .filter(Image.owner_id == owner_id)
            .filter(Image.collection_id == collection_id)
            .filter(
                sa.func.bit_count(
                    sa.cast(
                        Image.phash.op("#")(sa.cast(phash_int, sa.BigInteger)),
                        sa.dialects.postgresql.BIT(64)
                    )
                ) <= cls.PHASH_THRESHOLD
            )
            .first()
        )

        return bool(candidate)

