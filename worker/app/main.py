import sys
import os
import asyncio
import logging

# Add shared directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db.database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker")

async def main():
    logger.info("Iniciando Worker de Hacker News Monitor...")
    
    # Intentar conectar a la base de datos
    try:
        await db.connect()
        logger.info("Conexión a la base de datos PostgreSQL establecida con éxito desde el Worker.")
    except Exception as e:
        logger.error(f"Fallo crítico al conectar a la base de datos: {e}")
        sys.exit(1)
        
    try:
        # Bucle continuo para mantener el worker activo
        while True:
            logger.info("Worker activo y en espera de tareas...")
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Cancelación recibida. Deteniendo el worker...")
    finally:
        await db.disconnect()
        logger.info("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker detenido por el usuario.")
