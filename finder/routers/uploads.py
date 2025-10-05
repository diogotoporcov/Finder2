from fastapi import APIRouter, UploadFile, File, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finder.db.session import get_db
from finder.db.models.user import User
from finder.services.auth_service import AuthService
from finder.services.upload_service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadOut(BaseModel):
    upload_session_id: str


@router.post("/", response_model=UploadOut)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    session_id = await UploadService.upload_files(
        files, user, db, request.app.state.embedder
    )

    return UploadOut(upload_session_id=session_id)
