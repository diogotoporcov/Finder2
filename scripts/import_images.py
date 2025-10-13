import argparse
import asyncio
import uuid
from pathlib import Path
from typing import List, Generator, TypeVar

import sqlalchemy as sa

from finder.config import config
from finder.db.models.collection import Collection
from finder.db.models.image import Image
from finder.db.models.image_fingerprint import ImageFingerprint
from finder.db.session import SessionLocal
from finder.services.embedding_service import EmbeddingService
from finder.utils.duplicates import detect_duplicate_sha256, detect_duplicate_phash, detect_duplicate_embedding
from finder.utils.files import get_mime_types, read_files, load_images_from_bytes, write_files_bytes, delete_files
from finder.utils.hashing import sha256_many, phash_many

T = TypeVar('T')


def batch_list(list_: List[T], n: int = 10) -> Generator[List[T], None, None]:
    for i in range(0, len(list_), n):
        yield list_[i:i+n]


async def import_images(
    target_collection_id: uuid.UUID,
    prevent_duplicates: bool,
    embedder: EmbeddingService = EmbeddingService.get_instance(),
    files_per_batch: int = 10
) -> None:
    print("[import] start")
    print(f"[import] target_collection_id set")
    print(f"[import] prevent_duplicates={prevent_duplicates}, files_per_batch={files_per_batch}")

    if not embedder.is_running():
        raise RuntimeError("Embedder is not running!")

    config.IMPORTS_PATH.mkdir(exist_ok=True, parents=True)
    print(f"[import] imports_dir={config.IMPORTS_PATH}")

    async with SessionLocal() as db:
        collection: Collection = (
            await db.scalar(
                sa.select(Collection).where(Collection.id == target_collection_id)
            )
        )

        if collection is None:
            print("[db] collection not found -> abort")
            raise ValueError(f"Collection with id `{target_collection_id}` not found.")

        print("[db] collection loaded")

    file_paths = [path for path in config.IMPORTS_PATH.iterdir() if path.is_file()]
    print(f"[scan] files_found={len(file_paths)} in {config.IMPORTS_PATH}")

    valid_files: List[Path] = []
    valid_file_mimes: List[str] = []
    mime_list = await get_mime_types(file_paths)
    allowed = set(config.ALLOWED_MIME_TYPES)
    for path, mime in zip(file_paths, mime_list):
        if mime not in allowed:
            continue
        valid_files.append(path)
        valid_file_mimes.append(mime)

    print(f"[filter] valid_files={len(valid_files)}")

    total_processed = 0
    total_written = 0
    total_deleted = 0
    total_duplicates = 0

    batches_files = list(batch_list(valid_files, files_per_batch))
    batches_mimes = list(batch_list(valid_file_mimes, files_per_batch))
    print(f"[batch] batches={len(batches_files)} size~{files_per_batch}")

    for idx, (paths, mimes) in enumerate(zip(batches_files, batches_mimes), start=1):
        print(f"[batch {idx}/{len(batches_files)}] size={len(paths)} -> load bytes")
        file_contents = await read_files(paths)
        pil_images = await load_images_from_bytes(file_contents)
        print(f"[batch {idx}] images_loaded={len(pil_images)} -> hashing")

        sha256_list = await sha256_many(file_contents)
        phash_list = await phash_many(pil_images, hash_size=8)
        print(f"[batch {idx}] hashes_done -> embeddings")
        embeddings = await embedder.embed(pil_images)
        print(f"[batch {idx}] embeddings_done")

        images: List[Image] = []
        fingerprints: List[ImageFingerprint] = []
        for path, mime, file_content, sha256, phash, embedding in zip(
            paths, mimes, file_contents, sha256_list, phash_list, embeddings
        ):
            uuid_ = uuid.uuid4()
            images.append(Image(
                id=uuid_,
                owner_id=collection.owner_id,
                collection_id=collection.id,
                original_filename=path.name,
                stored_filename=f"{uuid_}{path.suffix}",
                mime_type=mime,
                size_bytes=len(file_content)
            ))

            fingerprints.append(ImageFingerprint(
                image_id=uuid_,
                sha256=sha256,
                phash=int.from_bytes(phash, signed=True),
                embedding=embedding
            ))

        print(f"[batch {idx}] stage_db images={len(images)} fingerprints={len(fingerprints)}")

        try:
            db.add_all(images)
            db.add_all(fingerprints)
            await db.flush()
            print(f"[batch {idx}] db_flush_ok")

            duplicates: List[Path] = []
            if prevent_duplicates:
                print(f"[batch {idx}] duplicate_check start")
                for path, image, fingerprint in zip(paths, images, fingerprints):
                    dupe = await detect_duplicate_sha256(db, image.owner_id, image.collection_id, image.id)
                    dupe_type = "sha256" if dupe else None

                    if not dupe:
                        dupe = await detect_duplicate_phash(db, image.owner_id, image.collection_id, image.id)
                        dupe_type = "phash" if dupe else None

                    if not dupe:
                        dupe = await detect_duplicate_embedding(db, image.owner_id, image.collection_id, image.id)
                        dupe_type = "embedding" if dupe else None

                    if dupe:
                        print(f"[duplicate] {dupe_type} match detected for {image.original_filename}: {dupe}")

                    if dupe is not None:
                        duplicates.append(path)
                        await db.delete(image)
                        await db.delete(fingerprint)

                print(f"[batch {idx}] duplicate_check done dupes={len(duplicates)}")
                total_duplicates += len(duplicates)

            to_write = [
                (
                    content,
                    config.STORAGE_PATH
                    / "collections"
                    / str(collection.owner_id)
                    / str(collection.id)
                    / image.stored_filename
                )
                for content, path, image
                in zip(file_contents, paths, images)
                if path not in duplicates
            ]
            await write_files_bytes(to_write)
            written_count = len(to_write)
            total_written += written_count
            print(f"[batch {idx}] wrote_files={written_count}")

            to_delete = [path for path in paths if path not in duplicates]
            await delete_files(to_delete)
            deleted_count = len(to_delete)
            total_deleted += deleted_count
            print(f"[batch {idx}] deleted_from_imports={deleted_count}")

            await db.commit()
            print(f"[batch {idx}] db_commit_ok")

            total_processed += len(paths)

        except Exception as e:
            await db.rollback()
            name = e.__class__.__name__
            msg = str(e)
            if len(msg) > 200:
                msg = msg[:200] + "...(truncated)"
            print(f"[batch {idx}] ERROR {name}: {msg}")
            raise

    print("[import] done")
    print(f"[import] totals processed={total_processed} written={total_written} deleted={total_deleted} duplicates={total_duplicates}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Import image files into a Finder v2 collection. "
                    "Files are processed in batches, hashed, embedded, "
                    "and stored in the database and file system."
    )
    parser.add_argument(
        "--id",
        required=True,
        help="UUID of the target collection to import images into."
    )
    parser.add_argument(
        "--prevent-duplicates",
        action="store_true",
        help="Enable duplicate detection using SHA256, pHash, and embedding similarity."
    )
    parser.add_argument(
        "--files_per_batch",
        type=int,
        default=64,
        help="Number of files processed simultaneously per batch."
    )
    args = parser.parse_args()

    asyncio.run(import_images(
        uuid.UUID(args.collection_id),
        prevent_duplicates=args.prevent_duplicates,
        files_per_batch=args.files_per_batch
    ))
