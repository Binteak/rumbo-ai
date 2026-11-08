# Rumbo · Agente de viajes con IA

Agente de IA que planifica viajes completos (destino, clima, presupuesto e itinerario) usando un **loop agéntico escrito a mano** sobre la API de Claude. La interfaz muestra en directo cómo razona el agente: cada herramienta que decide usar, sus argumentos, el resultado y cuánto tarda.

**Angular 22 · TypeScript · Python · FastAPI · Claude API (tool use) · PostgreSQL · Redis · Server-Sent Events · Docker · Kubernetes · GitHub Actions**

![Rumbo](docs/screenshot.png)

## Qué demuestra este proyecto

- **Agente con herramientas sin frameworks.** El loop (modelo → herramientas → resultados → modelo) está implementado a mano en `backend/app/agent/loop.py`, sin LangChain, para controlar cada paso: límite de iteraciones, errores que vuelven al modelo para que se corrija y un historial que solo se guarda si el turno termina bien.
- **Herramientas tipadas con Pydantic.** Cada herramienta se define una vez con un modelo Pydantic: de ahí sale el JSON Schema que ve el modelo y la validación de lo que devuelve. Si el modelo envía argumentos inválidos, recibe el error y reintenta.
- **Streaming en tiempo real.** FastAPI emite cada paso del agente como Server-Sent Events y Angular los pinta al instante (fetch + ReadableStream, porque `EventSource` no admite POST).
- **Observabilidad.** Cada ejecución guarda pasos, llamadas a herramientas, errores, tokens y duración (`/api/stats`). La cabecera muestra la tasa de éxito y el consumo.
- **Proveedor de modelo intercambiable.** El loop habla con una interfaz `ModelProvider`. Hay dos implementaciones: Claude (`AnthropicProvider`) y un **modo demo** que funciona sin API key ni coste, ideal para enseñar el proyecto.
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

Sin `ANTHROPIC_API_KEY` en `backend/.env` arranca en **modo demo**. Con la clave, usa Claude (`AGENT_MODEL`, por defecto `claude-sonnet-5-5`).

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
| `postgres.yaml` | StatefulSet con volumen persistente (PVC) y Service |
| `redis.yaml` | Deployment y Service para sesiones y bloqueos |
| `hpa.yaml` | Autoescalado del backend de 2 a 6 pods por CPU |
| `ingress.yaml` | Entrada HTTP: `/api` al backend y `/` al frontend, sin buffering para el streaming |
| `configmap.yaml` / `secret.example.yaml` | Configuración y plantilla de secretos |
| `kustomization.yaml` | Lo agrupa todo para `kubectl apply -k` |

> ingress-nginx se usa aquí por sencillez para el clúster local. En producción conviene valorar Gateway API u otro controlador mantenido.

## Tests

```bash
cd backend && pytest && ruff check .
cd frontend && npx ng test --watch=false
```

Los tests del loop usan un proveedor falso con turnos predefinidos, así que no gastan llamadas a la API. Cubren la autocorrección tras un error de herramienta, el límite de iteraciones, que el historial no se corrompa si la API falla y que dos réplicas comparten sesión a través de Redis.

## Estructura

```
backend/
  app/agent/loop.py        Loop agéntico (generador de eventos)
  app/agent/tools.py       Herramientas + esquemas Pydantic
  app/agent/providers.py   Interfaz de modelo + Claude
  app/agent/demo.py        Proveedor demo sin API key
  app/main.py              API FastAPI + SSE
  app/db.py                SQLAlchemy 2.0 (viajes y trazas)
  app/sessions.py          Sesiones en memoria o Redis (con bloqueo distribuido)
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
- Búsqueda semántica de actividades con embeddings y pgvector.

> Los datos de destinos (clima, costes y actividades) son aproximados y sirven solo para la demostración.
