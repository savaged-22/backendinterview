import asyncio
import httpx
from datetime import datetime
from html.parser import HTMLParser
import re
from db.database import db
from app.core.config import logger, HN_URL, SCRAPER_INTERVAL_SECONDS

class HackerNewsHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stories = []
        self.current_story = None
        
        # State tracking
        self.in_athing_tr = False
        self.in_titleline = False
        self.in_title_link = False
        self.in_subtext_td = False
        self.in_score_span = False
        self.in_hnuser_a = False
        
        self.temp_title = ""
        self.temp_url = ""
        self.temp_external_id = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()
        
        # Check for story row
        if tag == "tr" and "athing" in classes:
            self.in_athing_tr = True
            self.temp_external_id = attrs_dict.get("id", "")
            self.temp_title = ""
            self.temp_url = ""
            
        elif self.in_athing_tr:
            if tag == "span" and "titleline" in classes:
                self.in_titleline = True
            elif self.in_titleline and tag == "a":
                # First link inside titleline is the main story link
                if not self.temp_url:
                    self.temp_url = attrs_dict.get("href", "")
                    self.in_title_link = True
                    
        # Check for subtext row (the row after athing tr)
        elif tag == "td" and "subtext" in classes:
            self.in_subtext_td = True
            
        elif self.in_subtext_td:
            if tag == "span" and "score" in classes:
                self.in_score_span = True
            elif tag == "a" and "hnuser" in classes:
                self.in_hnuser_a = True

    def handle_endtag(self, tag):
        if tag == "tr" and self.in_athing_tr:
            self.in_athing_tr = False
            self.in_titleline = False
            self.in_title_link = False
            # Save the partial story info (external_id, title, url)
            if self.temp_external_id:
                self.current_story = {
                    "objectID": self.temp_external_id,
                    "title": self.temp_title.strip(),
                    "url": self.temp_url,
                    "points": 0,
                    "author": "unknown",
                    "created_at": None
                }
                
        elif tag == "span" and self.in_titleline:
            self.in_titleline = False
        elif tag == "a" and self.in_title_link:
            self.in_title_link = False
        elif tag == "td" and self.in_subtext_td:
            self.in_subtext_td = False
            if self.current_story:
                # If url is relative (e.g. item?id=...), prepend base URL
                if self.current_story["url"] and self.current_story["url"].startswith("item?"):
                    self.current_story["url"] = f"https://news.ycombinator.com/{self.current_story['url']}"
                self.stories.append(self.current_story)
                self.current_story = None
                
        elif tag == "span" and self.in_score_span:
            self.in_score_span = False
        elif tag == "a" and self.in_hnuser_a:
            self.in_hnuser_a = False

    def handle_data(self, data):
        if self.in_title_link:
            self.temp_title += data
        elif self.in_score_span and self.current_story:
            # Parse points like "153 points"
            match = re.search(r"(\d+)\s+point", data)
            if match:
                self.current_story["points"] = int(match.group(1))
        elif self.in_hnuser_a and self.current_story:
            self.current_story["author"] = data.strip()


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

        # 2. Fetch HTML from Hacker News
        logger.info(f"Descargando HTML desde {HN_URL}...")
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            res = await client.get(HN_URL, headers=headers, timeout=15.0)
            
            if res.status_code != 200:
                raise Exception(f"Fallo al descargar la página de Hacker News: Código HTTP {res.status_code}")
                
            html_content = res.text

        # 3. Parse HTML using HackerNewsHTMLParser
        logger.info("Parseando contenido HTML...")
        parser = HackerNewsHTMLParser()
        parser.feed(html_content)
        unique_hits = parser.stories

        logger.info(f"Se obtuvieron {len(unique_hits)} historias de la página principal para analizar.")

        # 4. Process and match stories
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

        for story in unique_hits:
            title = story.get("title")
            obj_id = story.get("objectID")
            if not title or not obj_id:
                continue
                
            title_lower = title.lower()
            matched = any(kw in title_lower for kw in keyword_list)
            
            if matched:
                matched_count += 1
                url = story.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
                author_username = story.get("author") or "unknown"
                points = story.get("points") or 0
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

        # 5. Save scraping execution log
        duration = (datetime.now() - start_time).total_seconds()
        message = f"Scraping completado con éxito en {duration:.2f}s. Historias analizadas: {scanned_count}. Matches de palabras clave detectados: {matched_count}."
        logger.info(message)
        
        await db.scrapinglog.create(
            data={
                "status": "SUCCESS",
                "message": message
            }
        )
        
    except Exception as e:
        error_msg = f"Error durante la ejecución de scraping HTML: {str(e)}"
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

async def periodic_scraper_loop():
    logger.info(f"Iniciando bucle periódico de scraping (intervalo: {SCRAPER_INTERVAL_SECONDS}s)...")
    # Wait 10 seconds initially to let DB container fully wake up and complete startup migrations
    await asyncio.sleep(10)
    while True:
        try:
            await run_scraping_job()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en bucle periódico del scraper: {e}")
        await asyncio.sleep(SCRAPER_INTERVAL_SECONDS)
