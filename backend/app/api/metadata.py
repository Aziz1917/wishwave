import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.public import MetadataExtractRequest, MetadataExtractResponse
from app.services.metadata import MetadataExtractionError, extract_product_metadata

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.post("/extract", response_model=MetadataExtractResponse)
async def extract_metadata(
    payload: MetadataExtractRequest,
    _: AsyncSession = Depends(get_db),
    __=Depends(get_current_user),
) -> MetadataExtractResponse:
    try:
        metadata = await extract_product_metadata(str(payload.url))
    except MetadataExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 429, 451, 498}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Извините, сайт ограничил автоматическое чтение данных. "
                    "Попробуйте другую ссылку или заполните поля вручную."
                ),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не удалось загрузить страницу (код {exc.response.status_code})",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Извините, не удалось подключиться к сайту для автозаполнения.",
        ) from exc

    return MetadataExtractResponse(**metadata)
