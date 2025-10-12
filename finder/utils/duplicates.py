import uuid
from typing import Optional

import sqlalchemy as sa
import sqlalchemy.dialects
from sqlalchemy.ext.asyncio import AsyncSession

from finder.db.models.image import Image
from finder.db.models.image_fingerprint import ImageFingerprint


async def detect_duplicate_sha256(
        db: AsyncSession,
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

    return await db.scalar(duplicate_query)


async def detect_duplicate_phash(
        db: AsyncSession,
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

    bit_diff = sa.func.bit_count(
        sa.cast(
            ImageFingerprint.phash.op("#")(target_phash),
            sa.dialects.postgresql.BIT(64)
        )
    )

    duplicate_query = (
        sa.select(Image.id)
        .join(ImageFingerprint, ImageFingerprint.image_id == Image.id)
        .where(
            Image.owner_id == owner_id,
            Image.collection_id == collection_id,
            Image.id != image_id,
            bit_diff <= sa.literal(threshold, type_=sa.Integer),
        )
        .limit(1)
    )

    return await db.scalar(duplicate_query)


async def detect_duplicate_embedding(
        db: AsyncSession,
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

    similarity = sa.literal(1.0, type_=sa.Float) - (
        ImageFingerprint.embedding.op("<=>")(target_embedding)
    )

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

    return await db.scalar(duplicate_query)
