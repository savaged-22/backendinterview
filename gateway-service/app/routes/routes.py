import os
import httpx
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

api_router = APIRouter()

WORKER_URL = os.getenv("WORKER_SERVICE_URL", "http://worker-service:8001")
TIMEOUT_LIMIT = float(os.getenv("WORKER_TIMEOUT_SECONDS", 10.0))

_client: Optional[httpx.AsyncClient] = None

async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=WORKER_URL, timeout=TIMEOUT_LIMIT)
    return _client

async def forward_request(method: str, path: str, params: dict = None, json_data: dict = None):
    client = await get_client()
    try:
        response = await client.request(method, path, params=params, json=json_data)
        if response.is_error:
            try:
                err_detail = response.json().get("detail", "Error interno en el servicio de procesamiento")
            except Exception:
                err_detail = response.text or "Error interno en el servicio de procesamiento"
            raise HTTPException(
                status_code=response.status_code, 
                detail=err_detail
            )
        return response.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"El microservicio de procesamiento no se encuentra disponible de forma síncrona: {exc}"
        )

@api_router.get("/posts")
async def get_posts(
    search: Optional[str] = Query(None, description="Búsqueda por Título"),
    sort_by: Optional[str] = Query("date", description="Ordenamiento por fecha o puntos")
):
    params = {"search": search, "sort_by": sort_by}
    return await forward_request("GET", "/internal/posts", params=params)

@api_router.get("/keywords")
async def get_keywords():
    return await forward_request("GET", "/internal/keywords")
    
@api_router.post("/keywords")
async def create_keyword(keyword: str):
    # La API interna del worker espera {"word": keyword}
    return await forward_request("POST", "/internal/keywords", json_data={"word": keyword})
    
@api_router.delete("/keywords")
async def delete_keywords(
    word: Optional[str] = Query(None, alias="word", description="Palabra clave específica a eliminar."),
    id: Optional[str] = Query(None, alias="id", description="ID de palabra clave específica a eliminar.")
):
    params = {}
    if word:
        params["word"] = word
    if id:
        params["id"] = id
    return await forward_request("DELETE", "/internal/keywords", params=params)

@api_router.get("/logs")
async def get_logs():
    return await forward_request("GET", "/internal/logs")

@api_router.post("/scraping/trigger")
async def trigger_scraping():
    return await forward_request("POST", "/internal/scraping/trigger")