import sys
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Add worker directory and shared project directory to Python path absolutely
current_dir = os.path.dirname(os.path.abspath(__file__))
worker_dir = os.path.dirname(current_dir)
project_dir = os.path.dirname(worker_dir)

sys.path.append(worker_dir)
sys.path.append(project_dir)

from db.database import db
from app.core.config import logger
from app.services.scraper import periodic_scraper_loop
from app.api.endpoints import router as api_router

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

# Register routes
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8001 inside the container
    uvicorn.run(app, host="0.0.0.0", port=8001)
