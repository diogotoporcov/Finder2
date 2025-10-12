import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from finder.db.models.image_fingerprint import ImageFingerprint
from finder.db.models.image import Image


class DuplicateService:
    @staticmethod
    def detect_duplicate_sha256(
        db: Session,
        owner_id: uuid.UUID,
        collection_id: uuid.UUID,
        image_id: uuid.UUID
    ) -> Optional[uuid.UUID]:
        target_sha = (
            sa.select(ImageFingerprint.sha256)
            .join(Image, ImageFingerprint.image_id == Image.id)
            .where(
                Image.id == image_id,
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
            )
            .scalar_subquery()
        )

        duplicate_query = (
            sa.select(Image.id)
            .join(ImageFingerprint, ImageFingerprint.image_id == Image.id)
            .where(
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
                Image.id != image_id,
                ImageFingerprint.sha256 == target_sha,
            )
            .limit(1)
        )

        return db.scalar(duplicate_query)

    @staticmethod
    def detect_duplicate_phash(
        db: Session,
        owner_id: uuid.UUID,
        collection_id: uuid.UUID,
        image_id: uuid.UUID,
        threshold: int = 5
    ) -> Optional[uuid.UUID]:
        target_phash = (
            sa.select(ImageFingerprint.phash)
            .join(Image, ImageFingerprint.image_id == Image.id)
            .where(
                Image.id == image_id,
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
            )
            .scalar_subquery()
        )

        bit_diff = sa.func.bit_count(ImageFingerprint.phash.op("#")(target_phash))

        duplicate_query = (
            sa.select(Image.id)
            .join(ImageFingerprint, ImageFingerprint.image_id == Image.id)
            .where(
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
                Image.id != image_id,
                bit_diff <= threshold,
            )
            .limit(1)
        )

        return db.scalar(duplicate_query)

    @staticmethod
    def detect_duplicate_embedding(
            db: Session,
            owner_id: uuid.UUID,
            collection_id: uuid.UUID,
            image_id: uuid.UUID,
            threshold: float = 0.9
    ) -> Optional[uuid.UUID]:
        target_embedding = (
            sa.select(ImageFingerprint.embedding)
            .join(Image, ImageFingerprint.image_id == Image.id)
            .where(
                Image.id == image_id,
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
            )
            .scalar_subquery()
        )

        similarity = 1 - (ImageFingerprint.embedding.op("<=>")(target_embedding))

        duplicate_query = (
            sa.select(Image.id)
            .join(ImageFingerprint, ImageFingerprint.image_id == Image.id)
            .where(
                Image.owner_id == owner_id,
                Image.collection_id == collection_id,
                Image.id != image_id,
                similarity >= sa.literal(threshold),
            )
            .limit(1)
        )

        return db.scalar(duplicate_query)
