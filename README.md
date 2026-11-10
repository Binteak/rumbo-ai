# Rumbo · Agente de viajes con IA

Agente de IA que planifica viajes completos (destino, clima, presupuesto e itinerario) y responde dudas prácticas con **RAG** sobre guías de cada destino, usando un **loop agéntico escrito a mano** sobre la API de Claude. La interfaz muestra en directo cómo razona el agente: cada herramienta que decide usar, sus argumentos, el resultado y cuánto tarda.

**Angular 22 · TypeScript · Python · FastAPI · Claude API y Groq (tool use) · RAG (BM25 + embeddings, pgvector) · PostgreSQL · Redis · Server-Sent Events · Docker · Kubernetes · GitHub Actions**

![Rumbo](docs/screenshot.png)

## Qué demuestra este proyecto

- **Agente con herramientas sin frameworks.** El loop (modelo → herramientas → resultados → modelo) está implementado a mano en `backend/app/agent/loop.py`, sin LangChain, para controlar cada paso: límite de iteraciones, errores que vuelven al modelo para que se corrija y un historial que solo se guarda si el turno termina bien.
- **RAG híbrido hecho a mano.** El agente consulta guías prácticas (visados, dinero, transporte, seguridad, costumbres...) con búsqueda híbrida BM25 + embeddings fusionada con RRF, vectores en PostgreSQL/pgvector, citas de la fuente en cada respuesta y evals de recuperación en la CI. Detalles en [RAG](#rag-guías-prácticas-de-cada-destino).
- **Herramientas tipadas con Pydantic.** Cada herramienta se define una vez con un modelo Pydantic: de ahí sale el JSON Schema que ve el modelo y la validación de lo que devuelve. Si el modelo envía argumentos inválidos, recibe el error y reintenta.
- **Streaming en tiempo real.** FastAPI emite cada paso del agente como Server-Sent Events y Angular los pinta al instante (fetch + ReadableStream, porque `EventSource` no admite POST).
- **Observabilidad.** Cada ejecución guarda pasos, llamadas a herramientas, errores, tokens y duración (`/api/stats`). La cabecera muestra la tasa de éxito y el consumo.
- **Proveedor de modelo intercambiable.** El loop habla con una interfaz `ModelProvider`. Hay tres implementaciones: Claude (`AnthropicProvider`), cualquier API compatible con OpenAI como Groq (`OpenAICompatibleProvider`, con un modelo gratuito) y un **modo demo** que funciona sin API key ni coste.
- **IA real gratis y sin sorpresas.** Límites por IP, presupuesto diario de tokens por debajo de la cuota gratuita y paso automático al modo demo cuando se agotan: nadie puede generar costes ni romper la demo. Detalles en [Modelo gratuito y protección](#modelo-gratuito-y-protección-frente-a-abusos).
- **Seguridad básica.** El viaje final se recalcula en el servidor en lugar de confiar en datos largos generados por el modelo, la entrada está limitada y la clave de API nunca llega al frontend.
- **Backend sin estado, listo para escalar.** El historial de cada conversación y su bloqueo viven en Redis, y los datos en PostgreSQL. Cualquier réplica puede atender el siguiente mensaje, así que el backend escala horizontalmente en Kubernetes. Probado con 3 réplicas atendiendo la misma conversación.
- **Preparado para Kubernetes.** Probes de liveness (`/api/health`) y readiness (`/api/ready`, que comprueba PostgreSQL y Redis), recursos limitados, usuario sin privilegios, autoescalado (HPA), Ingress con streaming y creación de tablas segura con varias réplicas arrancando a la vez (advisory lock de PostgreSQL).
- **Calidad.** Tests de backend (pytest) y frontend (Vitest), lint con Ruff, validación de manifiestos con kubeconform, CI en GitHub Actions y Docker multi-stage.

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
    API[API] --> Loop[Loop agéntico]
    Loop --> Provider{ModelProvider}
    Provider --> Claude[Claude API]
    Provider --> Demo[Modo demo]
    Loop --> Tools[Herramientas Pydantic]
    Tools --> Data[(Destinos)]
    Tools --> DB[(PostgreSQL)]
    Tools --> RAG[RAG híbrido · BM25 + vectores]
    RAG --> Guides[(Guías .md)]
    RAG --> PGV[(pgvector)]
    RAG -.-> Voyage[Voyage AI embeddings]
    API --> Redis[(Redis · sesiones)]
  end
```

En Kubernetes:

```mermaid
flowchart LR
  User((Usuario)) --> Ingress
  Ingress -- "/" --> FE[frontend · 2 pods]
  Ingress -- "/api" --> BE[backend · 2-6 pods · HPA]
  BE --> PG[(postgres · StatefulSet + PVC)]
  BE --> RD[(redis)]
  BE -.-> Secret[[Secret: API key, BD]]
  BE -.-> CM[[ConfigMap]]
```

Herramientas del agente:

| Herramienta | Qué hace |
|---|---|
| `search_destinations` | Puntúa destinos por intereses, mes, estilo y presupuesto |
| `get_climate` | Temperatura media y días de lluvia del mes |
| `estimate_budget` | Presupuesto por persona y total, desglosado |
| `build_itinerary` | Itinerario día a día con actividades reales del destino |
| `search_travel_guides` | RAG: busca en las guías prácticas y devuelve fragmentos con su fuente |
| `save_trip` | Guarda el viaje (recalculado en el servidor) |

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

Sin claves en `backend/.env` arranca en **modo demo**. Con `ANTHROPIC_API_KEY` usa Claude (`AGENT_MODEL`, por defecto `claude-sonnet-5-5`); con `GROQ_API_KEY`, un modelo gratuito de Groq (`GROQ_MODEL`, por defecto `openai/gpt-oss-120b`).

En local no hace falta nada más: sin `DATABASE_URL` usa SQLite y sin `REDIS_URL` guarda las sesiones en memoria.

### Con Docker (PostgreSQL + Redis + 2 réplicas)

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
| `redis.yaml` | Deployment y Service para sesiones y bloqueos |
| `hpa.yaml` | Autoescalado del backend de 2 a 6 pods por CPU |
| `ingress.yaml` | Entrada HTTP: `/api` al backend y `/` al frontend, sin buffering para el streaming |
| `configmap.yaml` / `secret.example.yaml` | Configuración y plantilla de secretos |
| `kustomization.yaml` | Lo agrupa todo para `kubectl apply -k` |

> ingress-nginx se usa aquí por sencillez para el clúster local. En producción conviene valorar Gateway API u otro controlador mantenido.

## Modelo gratuito y protección frente a abusos

Para que la demo pública use un modelo real **sin coste**, Rumbo puede usar el plan gratuito de [Groq](https://console.groq.com) (sin tarjeta) a través de `OpenAICompatibleProvider`, que también sirve para Gemini u OpenRouter cambiando `GROQ_BASE_URL` y `GROQ_MODEL`. El historial se guarda en un formato neutro, así que el proveedor puede cambiar a mitad de una conversación.

Sin método de pago no hay factura posible; además, la app se protege en tres capas (`backend/app/limits.py`):

| Capa | Qué hace | Por defecto |
|---|---|---|
| Anti-flood por IP | Más peticiones por minuto de las permitidas → HTTP 429 | 20 / minuto |
| Cupo de IA real por IP | Al agotarlo, esa persona sigue usando Rumbo **en modo demo**, con un aviso | 5 / hora, 15 / día |
| Presupuesto global de tokens | Al agotarlo, todo el mundo pasa al modo demo. Queda por debajo de los 200.000 tokens/día del plan gratuito | 180.000 / día |

- Los tokens servidos desde la caché del proveedor no se descuentan (Groq no los cuenta en sus cuotas).
- Si el proveedor responde 429 con una espera corta (límite por minuto), el agente espera y reintenta; si la espera es larga, se activa un *cooldown* global y el turno continúa en modo demo sin error (`app/agent/guard.py`).
- Los contadores van en Redis si hay `REDIS_URL` (compartidos entre réplicas) y en memoria si no.
- La cabecera muestra "IA real · modelo · te quedan N" o "Modo demo", y `GET /api/usage` devuelve el cupo de quien pregunta.

## RAG: guías prácticas de cada destino

Además de planificar, Rumbo responde dudas prácticas ("¿necesito visado para Japón?", "¿se deja propina en Nueva York?", "¿es seguro Ciudad del Cabo de noche?") **sin responder de memoria**: busca en una base de conocimiento propia y cita la fuente.

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
    RRF --> Top[Top-k con fuente y puntuaciones] --> LLM[Claude responde citando la guía]
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

### Probarlo

- En el chat: "¿Necesito visado para viajar a Japón?" o, después de planificar Lisboa, "¿y cómo me muevo por allí?" (usa el destino de la conversación).
- Por API: `GET /api/rag/search?q=propinas&destination_id=nuevayork` y `GET /api/rag/status` (embedder, almacén y nº de fragmentos).
- Con Docker Compose o Kubernetes los vectores se guardan en pgvector; en local con SQLite, en memoria.

> Las guías son orientativas y están revisadas a noviembre de 2026. Los requisitos de entrada cambian: el agente recuerda verificarlos en las fuentes oficiales.

## Tests

```bash
cd backend && pytest && ruff check .
cd backend && python -m evals.rag_eval    # evals del RAG
cd frontend && npx ng test --watch=false
```

Los tests del loop usan un proveedor falso con turnos predefinidos, así que no gastan llamadas a la API. Cubren la autocorrección tras un error de herramienta, el límite de iteraciones, que el historial no se corrompa si la API falla y que dos réplicas comparten sesión a través de Redis. Los del RAG cubren chunking, ingesta incremental, búsqueda híbrida, degradación a BM25, el cliente de Voyage (con un transporte HTTP simulado) y, en la CI, el almacén pgvector contra un PostgreSQL real.

## Estructura

```
backend/
  app/agent/loop.py        Loop agéntico (generador de eventos)
  app/agent/tools.py       Herramientas + esquemas Pydantic
  app/agent/providers.py   Interfaz de modelo + Claude + APIs compatibles con OpenAI (Groq)
  app/agent/demo.py        Proveedor demo sin API key
  app/agent/guard.py       Modelo real con presupuesto y paso automático al modo demo
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

## Próximos pasos

- Aprobación humana de herramientas desde la interfaz.
- Exponer las herramientas como servidor MCP.
- Migraciones con Alembic ejecutadas como Job de Kubernetes antes de cada despliegue.
- Reranker (por ejemplo, de Voyage) sobre los candidatos del RAG y evals de la respuesta final con un LLM como juez.

> Los datos de destinos (clima, costes y actividades) son aproximados y sirven solo para la demostración.
