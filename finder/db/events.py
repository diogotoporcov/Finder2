from sqlalchemy import event, insert, Connection
from sqlalchemy.orm import Mapper

from finder.db.models.collection import Collection
from finder.db.models.user import User


@event.listens_for(User, "after_insert")
def create_default_collection(_mapper: Mapper, connection: Connection, target: User):
    connection.execute(
        insert(Collection).values(
            owner_id=target.id,
            name="DEFAULT",
            is_default=True,
        )
    )


class DefaultCollectionDeletion(Exception):
    pass


@event.listens_for(Collection, "before_delete")
def prevent_default_collection_delete(_mapper: Mapper, _connection: Connection, target: Collection):
    if target.is_default:
        raise DefaultCollectionDeletion("Cannot delete the default collection.")
