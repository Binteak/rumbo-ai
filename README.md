# Rumbo · Agente de viajes con IA

Agente de IA que **planifica viajes completos** (destino, clima, presupuesto e itinerario) y **resuelve dudas prácticas** (visados, transporte, propinas, seguridad...) con RAG sobre guías propias, citando la fuente. Está construido con un **loop agéntico escrito a mano**, sin frameworks, y funciona con Claude, con modelos gratuitos (Gemini o Groq) o en modo demo sin coste. La interfaz muestra en directo cómo razona el agente: cada herramienta que decide usar, sus argumentos, el resultado y cuánto tarda.

**Angular 22 · TypeScript · Python · FastAPI · Claude, Gemini y Groq (tool calling) · RAG (BM25 + embeddings, pgvector) · PostgreSQL · Redis · Server-Sent Events · Docker · Kubernetes · GitHub Actions**

![Rumbo](docs/screenshot.png)

## Qué hace

- **Planifica un viaje a partir de una frase.** "5 días en Kioto en abril con mi pareja, gastronomía e historia": el agente busca el destino si no lo has decidido, consulta el clima del mes, calcula el presupuesto desglosado y genera un itinerario día a día con actividades reales. El viaje se guarda y se muestra en un panel.
- **Responde dudas prácticas con fuentes.** "¿Necesito visado para Japón?", "¿se deja propina en Nueva York?": busca en guías propias de cada destino y cita la sección de donde sale la respuesta. Si las guías no lo cubren, lo dice en lugar de inventar.
- **Recuerda la conversación.** Después de planificar Lisboa, "¿y cómo me muevo por allí?" o "mejor 2 días" se entienden sin repetir el destino.
- **Enseña cómo piensa.** La traza en vivo muestra cada paso del agente, las herramientas, los fragmentos recuperados por el RAG, los tokens y el tiempo.
- **Se mantiene en su tema.** Solo habla de viajes: a "¿quién juega hoy al fútbol?" responde que solo ayuda con viajes.
- **Es gratis de usar y de mantener.** Con un modelo gratuito y límites de uso, nadie puede generar costes ni romper la demo: si se agota la cuota, sigue funcionando en modo demo.

## Stack

| Capa | Tecnologías |
|---|---|
| Frontend | Angular 22 (signals, componentes standalone), TypeScript, SCSS, streaming con `fetch` + `ReadableStream` |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Server-Sent Events |
| IA | Loop agéntico propio con tool calling; Claude (Anthropic), Gemini y Groq vía API compatible con OpenAI; modo demo sin modelo |
| RAG | Chunking por secciones, BM25 + embeddings (Voyage AI o local) fusionados con RRF, pgvector, evals de recuperación |
| Datos | PostgreSQL + pgvector (SQLite en local), Redis para sesiones, bloqueos y límites de uso |
| Infra | Docker multi-stage, Docker Compose, Kubernetes (kustomize, HPA, Ingress, probes), nginx, Render |
| Calidad | pytest, Vitest, Ruff, kubeconform, GitHub Actions (tests, evals, build de imágenes) |

## Qué demuestra este proyecto

- **Agente con herramientas sin frameworks.** El loop (modelo → herramientas → resultados → modelo) está implementado a mano en `backend/app/agent/loop.py`, sin LangChain, para controlar cada paso: límite de iteraciones, errores que vuelven al modelo para que se corrija y un historial que solo se guarda si el turno termina bien.
- **RAG híbrido hecho a mano.** Búsqueda BM25 + embeddings fusionada con Reciprocal Rank Fusion, vectores en PostgreSQL/pgvector, citas de la fuente en cada respuesta y evals de recuperación que bloquean la CI si la calidad baja. Detalles en [RAG](#rag-guías-prácticas-de-cada-destino).
- **Proveedor de modelo intercambiable.** El loop habla con una interfaz `ModelProvider` con tres implementaciones: Claude (`AnthropicProvider`), cualquier API compatible con OpenAI como Gemini o Groq (`OpenAICompatibleProvider`) y un **modo demo** sin API key. El historial se guarda en un formato neutro, así que se puede cambiar de proveedor a mitad de una conversación.
- **IA real gratis y sin sorpresas.** Anti-flood por IP, cupo de IA real por persona y presupuesto diario de tokens por debajo de la cuota gratuita, con paso automático al modo demo. Detalles en [Modelo gratuito y protección](#modelo-gratuito-y-protección-frente-a-abusos).
- **Guardarraíles: el servidor no confía en el modelo para lo importante.** El viaje se recalcula en el servidor en lugar de usar datos largos generados por el modelo; si el modelo genera el itinerario pero olvida guardarlo, lo guarda el servidor; el agente rechaza los temas ajenos a los viajes. Detalles en [Guardarraíles](#guardarraíles).
- **Herramientas tipadas con Pydantic.** Cada herramienta se define una vez con un modelo Pydantic: de ahí sale el JSON Schema que ve el modelo y la validación de lo que devuelve. Si el modelo envía argumentos inválidos, recibe el error y reintenta.
- **Streaming en tiempo real.** FastAPI emite cada paso del agente como Server-Sent Events y Angular los pinta al instante (`fetch` + `ReadableStream`, porque `EventSource` no admite POST).
- **Observabilidad.** Cada ejecución guarda pasos, llamadas a herramientas, errores, tokens y duración (`/api/stats`). La traza muestra cada paso en directo y la cabecera, la tasa de éxito, el consumo y el modo activo.
- **Backend sin estado, listo para escalar.** El historial de cada conversación, su bloqueo y los contadores de uso viven en Redis, y los datos en PostgreSQL. Cualquier réplica puede atender el siguiente mensaje, así que el backend escala horizontalmente. Probado con 3 réplicas atendiendo la misma conversación.
- **Preparado para Kubernetes.** Probes de liveness (`/api/health`) y readiness (`/api/ready`, que comprueba PostgreSQL y Redis), recursos limitados, usuario sin privilegios, autoescalado (HPA), Ingress con streaming y creación de tablas segura con varias réplicas arrancando a la vez (advisory lock de PostgreSQL).
- **Calidad.** 75 tests de backend (pytest) y 4 de frontend (Vitest), evals del RAG, lint con Ruff, validación de manifiestos con kubeconform y CI en GitHub Actions. Los cambios entran por Pull Request con la CI en verde.

## Arquitectura

```mermaid
flowchart LR
  subgraph Frontend [Angular 22 · signals]
    Chat[Chat] --> Store[AgentStore]
    Store --> Trace[Traza en vivo]
    Store --> Trip[Vista del viaje]
  end
  Store -- "POST /api/chat (SSE)" --> API
  subgraph Backend [FastAPI]
    API[API] --> Limits[Límites de uso]
    API --> Loop[Loop agéntico]
    Loop --> Guard[Modelo protegido · presupuesto y fallback]
    Guard --> Provider{ModelProvider}
    Provider --> Claude[Claude]
    Provider --> OAI[Gemini / Groq]
    Provider --> Demo[Modo demo]
    Loop --> Tools[Herramientas Pydantic]
    Tools --> Data[(Destinos)]
    Tools --> DB[(PostgreSQL)]
    Tools --> RAG[RAG híbrido · BM25 + vectores]
    RAG --> Guides[(Guías .md)]
    RAG --> PGV[(pgvector)]
    RAG -.-> Voyage[Voyage AI embeddings]
    API --> Redis[(Redis · sesiones y contadores)]
  end
```

En Kubernetes:

```mermaid
flowchart LR
  User((Usuario)) --> Ingress
  Ingress -- "/" --> FE[frontend · 2 pods]
  Ingress -- "/api" --> BE[backend · 2-6 pods · HPA]
  BE --> PG[(postgres + pgvector · StatefulSet + PVC)]
  BE --> RD[(redis)]
  BE -.-> Secret[[Secret: API keys, BD]]
  BE -.-> CM[[ConfigMap]]
```

### Herramientas del agente

| Herramienta | Qué hace |
|---|---|
| `search_destinations` | Puntúa destinos por intereses, mes, estilo y presupuesto |
| `get_climate` | Temperatura media y días de lluvia del mes |
| `estimate_budget` | Presupuesto por persona y total, desglosado |
| `build_itinerary` | Itinerario día a día con actividades reales del destino |
| `search_travel_guides` | RAG: busca en las guías prácticas y devuelve fragmentos con su fuente |
| `save_trip` | Guarda el viaje (recalculado en el servidor) |

### API

| Método y ruta | Qué hace |
|---|---|
| `POST /api/chat` | Envía un mensaje al agente y devuelve cada paso en streaming (Server-Sent Events) |
| `POST /api/sessions/{id}/reset` | Empieza una conversación nueva |
| `GET /api/trips` · `GET /api/trips/{id}` · `DELETE /api/trips/{id}` | Viajes guardados |
| `GET /api/destinations` | Catálogo de destinos |
| `GET /api/rag/search?q=...&destination_id=...` | La misma búsqueda que usa el agente, para depurar y enseñar el RAG |
| `GET /api/rag/status` | Embedder, almacén de vectores y nº de fragmentos indexados |
| `GET /api/usage` | Modo con el que se atenderá a quien pregunta y cuántas consultas con IA real le quedan |
| `GET /api/stats` | Métricas agregadas: ejecuciones, tasa de éxito, pasos, herramientas, errores y tokens |
| `GET /api/health` · `GET /api/ready` | Liveness y readiness (PostgreSQL y Redis) |

Documentación interactiva (OpenAPI) en `/docs` al arrancar el backend.

## Modelo gratuito y protección frente a abusos

Para que la demo pública use un modelo real **sin coste**, Rumbo puede usar el plan gratuito de [Gemini](https://aistudio.google.com) o de [Groq](https://console.groq.com), ambos sin tarjeta, a través de `OpenAICompatibleProvider`. El proveedor se elige por variables de entorno, por prioridad: `ANTHROPIC_API_KEY` → Claude, `GEMINI_API_KEY` → Gemini (`gemini-flash-latest`), `GROQ_API_KEY` → Groq (`openai/gpt-oss-120b`) y, sin ninguna, modo demo.

- **Gemini 3:** las llamadas a herramientas llevan una *thought signature* que hay que reenviar en el siguiente turno; el proveedor la conserva en el historial.
- **Menos tokens por consulta:** el modelo recibe una vista compacta de los resultados grandes (el itinerario pasa de ~1.400 a ~500 caracteres), mientras que la interfaz recibe el detalle completo. Como cada resultado se reenvía en todas las llamadas siguientes del turno, el ahorro se multiplica.
- **Razonamiento en nivel bajo** (`reasoning_effort: low`) para no gastar cuota en tokens de razonamiento.

Sin método de pago en el proveedor no hay factura posible. Además, la app se protege en tres capas (`backend/app/limits.py`):

| Capa | Qué hace | Por defecto | Variable |
|---|---|---|---|
| Anti-flood por IP | Más peticiones por minuto de las permitidas → HTTP 429 | 20 / minuto | `RATE_LIMIT_FLOOD_PER_MINUTE` |
| Cupo de IA real por IP | Al agotarlo, esa persona sigue usando Rumbo **en modo demo**, con un aviso | 5 / hora, 15 / día | `RATE_LIMIT_LLM_PER_HOUR`, `RATE_LIMIT_LLM_PER_DAY` |
| Presupuesto global de tokens | Al agotarlo, todo el mundo pasa al modo demo | 180.000 / día | `LLM_DAILY_TOKEN_BUDGET` |

- La IP real se obtiene de `CF-Connecting-IP` detrás de Cloudflare (Render) o de la última entrada de `X-Forwarded-For` detrás de un proxy propio (nginx, Ingress). Aunque alguien falseara la cabecera, el presupuesto global sigue limitando el gasto total.
- Los tokens servidos desde la caché del proveedor no se descuentan, porque el proveedor tampoco los cuenta en sus cuotas.
- Si el proveedor responde 429 con una espera corta (límite por minuto), el agente espera y reintenta; si la espera es larga, se activa un *cooldown* global y el turno continúa en modo demo sin error (`app/agent/guard.py`).
- Los contadores van en Redis si hay `REDIS_URL` (compartidos entre réplicas) y en memoria si no.
- La cabecera muestra "IA real · modelo · te quedan N" o "Modo demo", y los avisos aparecen en el chat y en la traza.

## Guardarraíles

| Riesgo | Cómo se controla |
|---|---|
| El modelo inventa datos del viaje | `save_trip` solo recibe parámetros; el itinerario, el clima y el presupuesto se recalculan en el servidor con las mismas herramientas |
| El modelo olvida guardar el viaje | Si en el turno se generó un itinerario y no se guardó, el servidor lo guarda con los argumentos ya validados y lo indica en la traza |
| Argumentos inválidos | Validación Pydantic: el error vuelve al modelo como `is_error` y se corrige en el siguiente paso |
| Bucles infinitos | Máximo de 12 pasos por turno |
| Preguntas fuera de tema | El prompt limita el alcance a viajes y resiste los intentos de cambiar las reglas; el modo demo aplica la misma regla |
| Respuestas sin fuente sobre requisitos de entrada | Las dudas prácticas se responden solo con las guías, citando la sección; si no hay resultados, se dice |
| Entrada abusiva | Mensajes de máximo 1.000 caracteres y límites de uso por IP |
| Fugas de credenciales | Las claves solo existen en las variables de entorno del backend; nunca llegan al navegador |

## RAG: guías prácticas de cada destino

Además de planificar, Rumbo responde dudas prácticas **sin responder de memoria**: busca en una base de conocimiento propia y cita la fuente.

```mermaid
flowchart LR
  subgraph Ingesta [Ingesta · al arrancar, incremental]
    MD[Guías .md] --> Chunk[Chunking por sección] --> Emb[Embeddings] --> Store[(pgvector / memoria)]
  end
  subgraph Consulta [Consulta · herramienta search_travel_guides]
    Q[Pregunta] --> Exp[Detección de destino + expansión de consulta]
    Exp --> BM25[BM25]
    Exp --> Vec[Búsqueda vectorial]
    BM25 --> RRF[Fusión RRF]
    Vec --> RRF
    RRF --> Top[Top-k con fuente y puntuaciones] --> LLM[El modelo responde citando la guía]
  end
  Store --> Vec
```

| Pieza | Decisión y motivo |
|---|---|
| Base de conocimiento | `backend/app/data/guides/*.md`: una guía por destino (10 guías, 84 fragmentos). |
| Chunking | Por sección `##`: cada fragmento responde a un tema completo y la cita "Guía de Kioto · Cómo moverse" tiene sentido. Las secciones largas se dividen con solapamiento de una frase. Cada vector incluye destino y sección como contexto. |
| Embeddings | Interfaz `Embedder` con dos implementaciones: **Voyage AI** (`voyage-4-lite`, multilingüe, el proveedor que recomienda Anthropic) si hay `VOYAGE_API_KEY`, y un **embedder local por hashing** sin coste ni red para la demo, los tests y la CI. |
| Almacén | Interfaz `VectorStore`: **PostgreSQL + pgvector** (similitud coseno con `<=>`) cuando la BD es PostgreSQL, y memoria con SQLite. Cada fila guarda qué embedder la generó, así que cambiar de embedder reindexa sin mezclar vectores. |
| Búsqueda | **Híbrida**: BM25 acierta con términos exactos ("ESTA", "OMNY") y los vectores con sinónimos; se combinan con **Reciprocal Rank Fusion** porque sus puntuaciones no son comparables. Si la pregunta nombra un destino, se filtra por él. |
| Ingesta | Incremental por hash de contenido: solo se recalculan los fragmentos nuevos o modificados. Se ejecuta al arrancar (con bloqueo de PostgreSQL para varias réplicas) o con `python -m app.rag.ingest`. |
| Fiabilidad | Si el servicio de embeddings falla, la búsqueda sigue solo con BM25 y lo indica (`retrieval: "bm25"`). Si Voyage falla al arrancar, se usa el embedder local. Si no hay resultados, la herramienta pide al modelo que lo diga en vez de inventar. |
| Observabilidad | La traza muestra cada fragmento recuperado con su fuente, su posición en BM25 y en la búsqueda vectorial y el tiempo de cada parte. |

### Evals de recuperación

`backend/evals/rag_questions.jsonl` tiene 36 preguntas redactadas con palabras distintas a las de las guías, cada una con el fragmento que debería encontrarse. `python -m evals.rag_eval` mide:

| Escenario (embedder local) | hit@1 | recall@4 | MRR |
|---|---|---|---|
| Con destino (como lo usa el agente) | 0,92 | 1,00 | 0,96 |
| Sin destino (lo tiene que deducir) | 0,81 | 0,94 | 0,87 |

La CI ejecuta los evals en cada push y **falla si recall@4 baja de 0,9**, así que un cambio en las guías o en el retriever que empeore la búsqueda no llega a `main`. Los parámetros de la fusión (k de RRF y peso del ranking vectorial) se eligieron con este conjunto; con 36 preguntas hay riesgo de sobreajuste, por eso las preguntas no repiten la redacción de las guías. Con `--embedder voyage` se evalúa con embeddings semánticos reales.

> Las guías son orientativas y están revisadas a noviembre de 2026. Los requisitos de entrada cambian: el agente recuerda verificarlos en las fuentes oficiales.

## Pruébalo

- **Planificar:** "5 días en Kioto en abril con mi pareja, gastronomía e historia".
- **Ajustar:** a continuación, "mejor 3 días" o "hazlo más económico".
- **Dudas prácticas (RAG):** "¿Necesito visado para viajar a Japón?" o, después de planificar Lisboa, "¿y cómo me muevo por allí?".
- **Fuera de tema:** "¿quién juega hoy al fútbol?" → responde que solo ayuda con viajes.

## Arrancar en local

Requisitos: Python 3.11+ y Node 20.19+.

**En Windows, lo más rápido:** doble clic en `iniciar.bat`. Instala lo necesario la primera vez, abre backend y frontend y lanza el navegador en http://localhost:4200.

O a mano:

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload   # http://localhost:8000/docs

# Frontend (otra terminal)
cd frontend
npm install
npm start                       # http://localhost:4200
```

Sin claves en `backend/.env` arranca en **modo demo**. Con `ANTHROPIC_API_KEY` usa Claude (`AGENT_MODEL`, por defecto `claude-sonnet-5-5`); con `GEMINI_API_KEY`, Gemini gratis (`GEMINI_MODEL`, por defecto `gemini-flash-latest`); con `GROQ_API_KEY`, Groq gratis (`GROQ_MODEL`, por defecto `openai/gpt-oss-120b`).

En local no hace falta nada más: sin `DATABASE_URL` usa SQLite y sin `REDIS_URL` guarda las sesiones y los contadores en memoria.

### Despliegue en Render (demo pública)

- **Backend:** Web Service con el código de `backend/` (su `Dockerfile`, o `pip install -r requirements.txt` y `uvicorn app.main:app --host 0.0.0.0 --port $PORT`). Variables: `GEMINI_API_KEY` (o `GROQ_API_KEY`), `CORS_ORIGINS` con la URL del frontend y, opcionalmente, los límites de uso. **No** definas `ANTHROPIC_API_KEY` ni `AGENT_MODE=demo` si quieres el modelo gratuito.
- **Frontend:** Static Site con `npx ng build --configuration render`, que apunta la API al backend desplegado (`src/environments/environment.render.ts`).
- En el plan gratuito, la base de datos SQLite se pierde al reiniciar o desplegar, y el RAG se reindexa en memoria al arrancar (milisegundos).

### Con Docker (PostgreSQL + pgvector + Redis + 2 réplicas)

```bash
docker compose up --build       # http://localhost:8080
```

### En Kubernetes (clúster local con kind)

Requisitos: Docker, [kind](https://kind.sigs.k8s.io/) y kubectl.

```bash
# 1. Clúster local con el puerto 80 expuesto y un Ingress controller
kind create cluster --name rumbo --config k8s/kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=120s

# 2. Imágenes construidas en local y cargadas en el clúster
docker build -t rumbo-backend:1.0.0 backend
docker build -t rumbo-frontend:1.0.0 frontend
kind load docker-image rumbo-backend:1.0.0 rumbo-frontend:1.0.0 --name rumbo

# 3. Secretos (fuera del repositorio) y despliegue
kubectl apply -f k8s/namespace.yaml
kubectl -n rumbo create secret generic rumbo-secrets \
  --from-literal=ANTHROPIC_API_KEY= \
  --from-literal=GEMINI_API_KEY= \
  --from-literal=GROQ_API_KEY= \
  --from-literal=VOYAGE_API_KEY= \
  --from-literal=POSTGRES_PASSWORD=cambia-esto \
  --from-literal=DATABASE_URL=postgresql+psycopg://rumbo:cambia-esto@postgres:5432/rumbo
kubectl apply -k k8s
kubectl -n rumbo get pods -w      # espera a que todo esté Running y Ready
```

Abre http://rumbo.localhost. Comandos útiles para la demo:

```bash
kubectl -n rumbo scale deployment backend --replicas=4   # escalar
kubectl -n rumbo rollout restart deployment backend      # despliegue sin cortes (rolling update)
kubectl -n rumbo logs -l app=backend -f                  # logs de todas las réplicas
kind delete cluster --name rumbo                         # borrar el clúster
```

| Manifiesto | Qué define |
|---|---|
| `backend.yaml` | Deployment (2 réplicas, rolling update sin caída, probes, límites de CPU/memoria, usuario no root) y Service |
| `frontend.yaml` | Deployment nginx con la app Angular y Service |
| `postgres.yaml` | StatefulSet de PostgreSQL con pgvector, volumen persistente (PVC) y Service |
| `redis.yaml` | Deployment y Service para sesiones, bloqueos y contadores de uso |
| `hpa.yaml` | Autoescalado del backend de 2 a 6 pods por CPU |
| `ingress.yaml` | Entrada HTTP: `/api` al backend y `/` al frontend, sin buffering para el streaming |
| `configmap.yaml` / `secret.example.yaml` | Configuración y plantilla de secretos |
| `kustomization.yaml` | Lo agrupa todo para `kubectl apply -k` |

> ingress-nginx se usa aquí por sencillez para el clúster local. En producción conviene valorar Gateway API u otro controlador mantenido.

## Tests

```bash
cd backend && pytest && ruff check .
cd backend && python -m evals.rag_eval    # evals del RAG
cd frontend && npx ng test --watch=false
```

Ningún test llama a un modelo real: se usan proveedores falsos con turnos predefinidos y transportes HTTP simulados con el formato de cada API.

- **Agente:** autocorrección tras un error de herramienta, límite de iteraciones, historial intacto si la API falla, guardado del viaje por el servidor y rechazo de temas ajenos.
- **Proveedores:** traducción del historial al formato de OpenAI, tool calls, *thought signatures* de Gemini, 429 con `retry-after` en cabecera y en el mensaje, y reintento ante llamadas mal formadas.
- **Protección:** anti-flood, cupos por IP con reloj simulado (memoria y Redis), presupuesto de tokens, *cooldown* y paso al modo demo de punta a punta.
- **RAG:** chunking, ingesta incremental, búsqueda híbrida, degradación a BM25, cliente de Voyage y, en la CI, el almacén pgvector contra un PostgreSQL real.
- **Sesiones:** dos réplicas comparten la conversación a través de Redis.

## Estructura

```
backend/
  app/agent/loop.py        Loop agéntico (generador de eventos) y guardado del viaje por el servidor
  app/agent/tools.py       Herramientas + esquemas Pydantic + vista compacta para el modelo
  app/agent/providers.py   Interfaz de modelo + Claude + APIs compatibles con OpenAI (Gemini, Groq)
  app/agent/guard.py       Modelo real con presupuesto, reintentos y paso automático al modo demo
  app/agent/demo.py        Proveedor demo sin API key
  app/limits.py            Anti-flood, cupo por IP y presupuesto diario de tokens
  app/main.py              API FastAPI + SSE
  app/db.py                SQLAlchemy 2.0 (viajes y trazas)
  app/sessions.py          Sesiones en memoria o Redis (con bloqueo distribuido)
  app/rag/                 RAG: chunking, embeddings, pgvector, búsqueda híbrida, ingesta
  app/data/guides/         Base de conocimiento: una guía práctica por destino
  evals/                   Evals de recuperación del RAG (preguntas + script)
  tests/                   pytest
k8s/                       Manifiestos de Kubernetes (kustomize)
frontend/
  src/app/core/            ApiService (SSE), AgentStore (signals), modelos
  src/app/components/      Chat, traza del agente, vista del viaje
```

## Historial de versiones

| Versión | Novedades |
|---|---|
| 1.0 | Agente con loop propio y herramientas tipadas, streaming de la traza, modo demo, Docker, Kubernetes y CI |
| 1.1 | RAG híbrido sobre guías de viaje (BM25 + embeddings, pgvector) con citas de fuentes y evals de recuperación en la CI |
| 1.2 | IA real gratis con Groq, protección frente a abusos (anti-flood, cupos por IP, presupuesto diario) y paso automático al modo demo |
| 1.3 | Gemini como proveedor gratuito, resultados compactos para el modelo (menos tokens por consulta), guardado del viaje garantizado por el servidor y guardarraíl de alcance |

## Limitaciones conocidas

- **Los viajes guardados son compartidos:** cualquier visitante ve los viajes de los demás y puede borrarlos, porque la API no distingue usuarios. No contienen datos personales, pero es lo primero de los próximos pasos.
- **El guardarraíl de alcance está en el prompt:** reduce mucho las respuestas fuera de tema, pero ningún prompt es infalible con un usuario insistente.
- **Persistencia en la demo pública:** en el plan gratuito de Render la base de datos SQLite se pierde con cada despliegue o reinicio.
- **Cuotas gratuitas:** con mucho tráfico, la IA real se agota antes y la app pasa al modo demo (por diseño, sin errores ni costes).
- **Datos de ejemplo:** el clima, los costes y las actividades de los destinos son aproximados y sirven para la demostración.

## Próximos pasos

**Producto**
- **Viajes privados por usuario:** asociar cada viaje a la sesión del visitante (y más adelante a una cuenta con login) para que cada persona vea y borre solo los suyos, con autorización en `GET` y `DELETE /api/trips`.
- Más destinos y guías, con un proceso para mantener actualizados los requisitos de entrada.
- Aprobación humana de herramientas desde la interfaz antes de guardar o modificar datos.
- Respuesta final en streaming token a token y soporte multiidioma.

**IA**
- Filtro de alcance en el servidor (un clasificador ligero antes de llamar al modelo) para blindar el guardarraíl y ahorrar cuota.
- Evals de la respuesta final con un LLM como juez (fidelidad a las fuentes, uso correcto de herramientas) además de los de recuperación.
- Reranker (por ejemplo, de Voyage) sobre los candidatos del RAG.
- Exponer las herramientas como servidor MCP para que otros agentes puedan usar Rumbo.

**Plataforma**
- PostgreSQL gestionado con pgvector en la demo pública para que los datos persistan entre despliegues.
- Migraciones con Alembic ejecutadas como Job de Kubernetes antes de cada despliegue.
- Trazas con OpenTelemetry (o Langfuse) para analizar latencia, coste y errores por paso en producción.
- Despliegue automático en Render al fusionar en `main`.
