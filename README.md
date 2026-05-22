# Hacker News Monitor - Backend & Microservicios

Este es el repositorio del backend para la prueba técnica de monitoreo de Hacker News. El backend está estructurado con una arquitectura de microservicios contenerizados utilizando **Docker** y **Docker Compose**.

## 1. Cómo correr el proyecto desde cero, paso a paso

### Requisitos previos
* **Docker** y **Docker Compose** instalados en el sistema.
* Permisos de superusuario (`sudo`) si el entorno Docker lo requiere.

### Instrucciones de despliegue

1. **Clonar/Ubicar los directorios del proyecto:**
   Asegúrate de tener los directorios `backendinterview` (este repositorio) y `hackernewsfront` en el mismo nivel jerárquico del sistema de archivos.

2. **Configurar variables de entorno (Opcional):**
   El archivo `.env` en la raíz contiene las variables por defecto para la base de datos PostgreSQL.
   ```env
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=password123
   POSTGRES_DB=hackernews
   ```

3. **Construir y levantar la arquitectura completa:**
   Ejecuta el siguiente comando en la raíz de este directorio para construir las imágenes Docker de todos los microservicios e inicializarlos:
   ```bash
   sudo docker compose up -d --build
   ```

4. **Verificar que todos los servicios estén en ejecución:**
   Puedes comprobar el estado de los contenedores ejecutando:
   ```bash
   sudo docker compose ps
   ```
   Deberías ver cinco contenedores con estado `Up` o `Up (healthy)`:
   * `postgres-db` (Puerto 5433 local -> 5432 interno)
   * `worker-service` (Puerto 8001)
   * `gateway-service` (Puerto 8000)
   * `hackernewsfront` (Puerto 3000)
   * `nginx-proxy` (Puerto 80)

5. **Aplicación automática del esquema de Base de Datos:**
   El `worker-service` ejecuta automáticamente `prisma db push` al iniciar, asegurando que las tablas se creen en PostgreSQL de inmediato sin intervención manual.

6. **Probar la API del Gateway:**
   * Healthcheck: `curl http://localhost:8000/health`
   * Obtener posts: `curl http://localhost:8000/posts`
   * Listar palabras clave: `curl http://localhost:8000/keywords`

---

## 2. Decisiones técnicas tomadas y justificación

* **Descentralización del Worker (`main.py`):**
  Se refactorizó el worker original descentralizando la lógica de `main.py` en una estructura modular basada en buenas prácticas de Clean Code:
  * `core/` para configuraciones seguras.
  * `services/` para la lógica pura de negocio (scraper).
  * `api/` para interfaces de comunicación.
  * `main.py` como único punto de entrada e inicialización de la app.

* **Scraping Directo de HTML (Parser Nativo):**
  En lugar de depender de la API de Algolia de Hacker News o de instalar librerías externas pesadas como BeautifulSoup, se implementó una subclase personalizada de `html.parser.HTMLParser` (módulo nativo de Python). Esto reduce la superficie de dependencias del microservicio, optimiza el consumo de memoria del contenedor y cumple de forma estricta las reglas de no incluir paquetes externos no aprobados.

* **Uso de Prisma ORM para Python:**
  Se eligió Prisma como ORM por la facilidad de tipado y autocompletado en Python, junto con su capacidad para definir y sincronizar el esquema declarativo en el archivo compartido `schema.prisma`.

* **Arquitectura Gateway-Worker:**
  El `gateway-service` actúa como el único punto de contacto público (API Gateway), validando y redirigiendo peticiones hacia la API interna del `worker-service`. Esto aísla la lógica pesada del scraping y las conexiones recurrentes de la base de datos de la interfaz pública externa.

---

## 3. Estructura del proyecto

El backend se organiza de la siguiente manera:

```text
backendinterview/
├── db/                       # Módulo compartido de base de datos
│   ├── database.py           # Instancia y conexión global de Prisma
│   └── prisma/
│       └── schema.prisma     # Definición del esquema declarativo de base de datos (Postgres)
├── gateway-service/          # Microservicio Gateway (punto de entrada de la API pública)
│   ├── app/
│   │   ├── core/             # Configuraciones básicas
│   │   ├── routes/           # Rutas públicas que retransmiten peticiones al Worker
│   │   └── main.py           # Inicializador de FastAPI para el Gateway
│   └── Dockerfile            # Construcción de la imagen de producción/dev del Gateway
├── nginx/                    # Configuración de Nginx para proxy reverso
│   └── nginx.conf            # Reglas de ruteo al frontend y gateway
├── worker/                   # Microservicio Worker (Scraper periódico y API interna)
│   ├── app/
│   │   ├── api/              # Endpoints locales (/internal/posts, /internal/keywords, etc.)
│   │   ├── core/             # Configuración centralizada de variables y logs
│   │   ├── services/         # Lógica de scraping y parsing HTML (scraper.py)
│   │   └── main.py           # Inicialización limpia, lifespan y prisma db push
│   ├── Dockerfile            # Imagen de construcción del Worker
│   └── requirements.txt      # Dependencias del Worker (Prisma, FastAPI, Uvicorn, Httpx)
├── docker-compose.yml        # Orquestador multi-contenedor
└── .env                      # Variables de entorno por defecto
```

---

## 4. Trade-offs e Implicaciones de Diseño

* **Concurrencia vs. Bloqueo de IP:**
  Al usar scraping directo de HTML en lugar de una API oficial, existe el riesgo de que la dirección IP del contenedor sea bloqueada por Hacker News ante demasiadas peticiones seguidas. Se configuró un intervalo por defecto de 60 segundos (`SCRAPER_INTERVAL_SECONDS`), pero un diseño ideal de producción requeriría un pool de proxies rotativos y un mecanismo de backoff exponencial en caso de errores `429` (Too Many Requests).
* **Ausencia de una cola de mensajería externa (RabbitMQ/Redis/Celery):**
  Actualmente, el worker ejecuta las tareas de scraping de fondo usando las tareas asíncronas de FastAPI (`asyncio.create_task` y `BackgroundTasks`). Esto simplifica la infraestructura al no requerir Redis o RabbitMQ, pero si el microservicio se escala horizontalmente a múltiples instancias, se duplicarían los scrapings en paralelo. Para producción, un broker de tareas sería mandatorio.

---

## 5. Uso de Inteligencia Artificial (IA)

En el desarrollo de este componente de backend, se utilizó IA bajo los siguientes alcances:
* **Backend:** Se solicitó asistencia para la refactorización y descentralización del código original en `main.py`, distribuyéndolo en paquetes modulares (`core`, `services`, `api`) bajo principios de Clean Code y mejoramiento de prácticas orientadas al diseño de microservicios.
* **Validación:** El código generado por IA fue verificado ejecutando pruebas unitarias directas en contenedores Docker y comprobando que la base de datos se poblaba de forma correcta.

*Texto requerido sobre IA:*
> Para el backend, se le pidió ayuda para la refactorización de código y mejoramiento de prácticas orientadas al código (clean code).
