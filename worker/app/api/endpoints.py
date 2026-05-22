from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from db.database import db
from app.core.config import logger
from app.services.scraper import run_scraping_job

router = APIRouter()

class KeywordCreate(BaseModel):
    word: str

@router.get("/internal/posts")
async def get_posts(
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("date")
):
    try:
        # Build query filters
        where = {}
        if search:
            where["title"] = {"contains": search, "mode": "insensitive"}

        # Define sorting order
        order = {}
        if sort_by == "points":
            order = {"points": "desc"}
        else:
            # Default or "date" sorting
            order = {"detectedAt": "desc"}

        posts = await db.post.find_many(
            where=where,
            include={"author": True},
            order=order
        )

        # Flatten post structure matching frontend contract
        return [
            {
                "id": post.id,
                "hnId": post.externalId or "",
                "title": post.title,
                "author": post.author.username if post.author else "unknown",
                "points": post.points,
                "url": post.url,
                "detectedAt": post.detectedAt.isoformat()
            }
            for post in posts
        ]
    except Exception as e:
        logger.error(f"Error al obtener posts en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener posts: {str(e)}")

@router.get("/internal/keywords")
async def get_keywords():
    try:
        keywords = await db.keyword.find_many()
        return [
            {
                "id": kw.id,
                "word": kw.keyword
            }
            for kw in keywords
        ]
    except Exception as e:
        logger.error(f"Error al obtener keywords en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener keywords: {str(e)}")

@router.post("/internal/keywords")
async def create_keyword(data: KeywordCreate):
    try:
        word_clean = data.word.strip()
        if not word_clean:
            raise HTTPException(status_code=400, detail="El keyword no puede estar vacío.")

        # Check if already exists to prevent duplicate constraint violation
        existing = await db.keyword.find_unique(where={"keyword": word_clean})
        if existing:
            return {"id": existing.id, "word": existing.keyword}

        kw = await db.keyword.create(
            data={"keyword": word_clean}
        )
        return {"id": kw.id, "word": kw.keyword}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al crear keyword en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear keyword: {str(e)}")

@router.delete("/internal/keywords")
async def delete_keywords(
    word: Optional[str] = Query(None),
    id: Optional[str] = Query(None)
):
    try:
        if id:
            id_clean = id.strip()
            existing = await db.keyword.find_unique(where={"id": id_clean})
            if not existing:
                raise HTTPException(status_code=404, detail=f"Keyword con ID '{id_clean}' no encontrado.")
            await db.keyword.delete(where={"id": id_clean})
            return {"message": f"Keyword con ID '{id_clean}' eliminado correctamente"}
        elif word:
            word_clean = word.strip()
            existing = await db.keyword.find_unique(where={"keyword": word_clean})
            if not existing:
                raise HTTPException(status_code=404, detail=f"Keyword '{word_clean}' no encontrado.")
            await db.keyword.delete(where={"keyword": word_clean})
            return {"message": f"Keyword '{word_clean}' en DB eliminado correctamente"}
        else:
            # Delete all keywords
            count = await db.keyword.delete_many()
            return {"message": "Todos los keywords eliminados correctamente", "deleted_count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al eliminar keywords en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar keywords: {str(e)}")

@router.get("/internal/logs")
async def get_logs():
    try:
        logs = await db.scrapinglog.find_many(
            order={"timestamp": "desc"},
            take=50  # Limit to the last 50 execution logs to keep it clean
        )
        return [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "status": log.status,
                "message": log.message
            }
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Error al obtener logs en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener logs: {str(e)}")

@router.post("/internal/scraping/trigger")
async def trigger_scraping(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(run_scraping_job)
        return {"status": "success", "message": "Proceso de scraping iniciado en segundo plano"}
    except Exception as e:
        logger.error(f"Error al disparar scraping manual en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al disparar scraping: {str(e)}")
