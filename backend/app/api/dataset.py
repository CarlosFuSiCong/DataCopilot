import logging
import uuid

from fastapi import APIRouter, File, UploadFile

from app.core.exceptions import InvalidDatasetError
from app.models.dataset import UploadResponse
from app.services import dataset_store, profiler as profiler_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise InvalidDatasetError("Only .csv files are accepted.")

    content = await file.read()
    profile = profiler_service.profile(content, file.filename)

    dataset_id = str(uuid.uuid4())
    dataset_store.save(dataset_id, content)

    return UploadResponse(dataset_id=dataset_id, profile=profile)
