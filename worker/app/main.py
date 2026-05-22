import sys
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

# Add shared directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
import httpx

from db.database import db

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker")

class KeywordCreate(BaseModel):
    word: str

# Background scraping logic
async def run_scraping_job():
    logger.info("Iniciando ejecución de scraping de Hacker News...")
    start_time = datetime.now()
    
    try:
        # 1. Fetch keywords from DB
        keywords = await db.keyword.find_many()
        if not keywords:
            logger.info("No hay palabras clave registradas en la base de datos. Saltando scraping.")
            await db.scrapinglog.create(
                data={
                    "status": "SUCCESS",
                    "message": "Scraping completado. Sin palabras clave registradas."
                }
            )
            return

        keyword_list = [k.keyword.lower().strip() for k in keywords if k.keyword]
        logger.info(f"Buscando historias que contengan alguna de las palabras clave: {keyword_list}")

        # 2. Fetch posts from Hacker News Algolia API (Front Page + New Stories)
        async with httpx.AsyncClient() as client:
            fp_url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
            new_url = "https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=50"
            
            logger.info("Consultando la API de Hacker News (Algolia)...")
            fp_res = await client.get(fp_url, timeout=10.0)
            new_res = await client.get(new_url, timeout=10.0)
            
            hits = []
            if fp_res.status_code == 200:
                hits.extend(fp_res.json().get("hits", []))
            if new_res.status_code == 200:
                hits.extend(new_res.json().get("hits", []))

        # Deduplicate hits by objectID
        unique_hits = {}
        for hit in hits:
            obj_id = hit.get("objectID")
            if obj_id:
                unique_hits[obj_id] = hit

        logger.info(f"Se obtuvieron {len(unique_hits)} historias únicas para analizar.")

        # 3. Process and match stories
        scanned_count = len(unique_hits)
        matched_count = 0
        
        # Ensure Hacker News source exists
        source = await db.source.find_first(where={"name": "Hacker News"})
        if not source:
            source = await db.source.create(
                data={
                    "name": "Hacker News",
                    "baseUrl": "https://news.ycombinator.com"
                }
            )

        for obj_id, hit in unique_hits.items():
            title = hit.get("title")
            if not title:
                continue
                
            title_lower = title.lower()
            matched = any(kw in title_lower for kw in keyword_list)
            
            if matched:
                matched_count += 1
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
                author_username = hit.get("author") or "unknown"
                points = hit.get("points") or 0
                created_at_str = hit.get("created_at")
                
                # Parse published timestamp
                published_at = None
                if created_at_str:
                    try:
                        published_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    except Exception:
                        published_at = datetime.now()
                else:
                    published_at = datetime.now()

                # Find or create Author
                author = await db.author.find_unique(where={"username": author_username})
                if not author:
                    author = await db.author.create(data={"username": author_username})

                # Find or create/update Post
                post = await db.post.find_unique(where={"externalId": obj_id})
                if not post:
                    post = await db.post.create(
                        data={
                            "externalId": obj_id,
                            "title": title,
                            "url": url,
                            "points": points,
                            "publishedAt": published_at,
                            "authorId": author.id,
                            "sourceId": source.id
                        }
                    )
                    # Create DetectionEvent
                    await db.detectionevent.create(
                        data={
                            "postId": post.id
                        }
                    )
                    logger.info(f"[NUEVO MATCH] Registrado post: '{title}' por @{author_username}")
                else:
                    # Update points
                    await db.post.update(
                        where={"id": post.id},
                        data={"points": points}
                    )
                    logger.info(f"[ACTUALIZADO] Puntos para '{title}': {points}")

        # 4. Save scraping execution log
        duration = (datetime.now() - start_time).total_seconds()
        message = f"Scraping completado con éxito en {duration:.2f}s. Historias analizadas: {scanned_count}. Matches detectados: {matched_count}."
        logger.info(message)
        
        await db.scrapinglog.create(
            data={
                "status": "SUCCESS",
                "message": message
            }
        )
        
    except Exception as e:
        error_msg = f"Error durante la ejecución de scraping: {str(e)}"
        logger.error(error_msg, exc_info=True)
        try:
            await db.scrapinglog.create(
                data={
                    "status": "FAILED",
                    "message": error_msg
                }
            )
        except Exception as db_err:
            logger.error(f"No se pudo persistir el log de error en base de datos: {db_err}")

# Periodic scraper loop
async def periodic_scraper_loop():
    logger.info("Iniciando bucle periódico de scraping (intervalo: 60s)...")
    # Wait 10 seconds initially to let DB container fully wake up and complete startup migrations
    await asyncio.sleep(10)
    while True:
        try:
            await run_scraping_job()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en bucle periódico del scraper: {e}")
        await asyncio.sleep(60)

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run database migrations / push schema
    try:
        logger.info("Aplicando/verificando esquema Prisma en la base de datos...")
        import subprocess
        # El directorio de trabajo es /app/worker, el esquema está en ../db/prisma/schema.prisma
        result = subprocess.run(
            ["prisma", "db", "push", "--schema=../db/prisma/schema.prisma", "--accept-data-loss"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Error al aplicar el esquema de Prisma:\nStdout: {result.stdout}\nStderr: {result.stderr}")
        else:
            logger.info("Esquema de Prisma aplicado/verificado exitosamente.")
            logger.info(result.stdout)
    except Exception as db_push_err:
        logger.error(f"Error inesperado ejecutando prisma db push: {db_push_err}")

    # Startup: Connect to DB
    try:
        await db.connect()
        logger.info("Conexión a la base de datos PostgreSQL establecida con éxito desde el Worker.")
    except Exception as e:
        logger.error(f"Fallo crítico al conectar a la base de datos desde el Worker: {e}")
        sys.exit(1)
        
    # Start background task
    scraper_task = asyncio.create_task(periodic_scraper_loop())
    
    yield
    
    # Shutdown: Clean up task and DB connection
    logger.info("Deteniendo Worker de Hacker News Monitor...")
    scraper_task.cancel()
    try:
        await scraper_task
    except asyncio.CancelledError:
        pass
    
    await db.disconnect()
    logger.info("Conexión a la base de datos cerrada desde el Worker.")

app = FastAPI(
    title="Worker & Scraping Service", 
    version="1.0.0",
    lifespan=lifespan
)

# API ENDPOINTS FOR GATEWAY PROXYING

@app.get("/internal/posts")
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

@app.get("/internal/keywords")
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

@app.post("/internal/keywords")
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

@app.delete("/internal/keywords")
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

@app.get("/internal/logs")
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

@app.post("/internal/scraping/trigger")
async def trigger_scraping(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(run_scraping_job)
        return {"status": "success", "message": "Proceso de scraping iniciado en segundo plano"}
    except Exception as e:
        logger.error(f"Error al disparar scraping manual en el Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Error al disparar scraping: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8001 inside the container
    uvicorn.run(app, host="0.0.0.0", port=8001)
