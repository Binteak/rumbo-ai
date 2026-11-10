"""Normalización de texto en español compartida por BM25 y el embedder local."""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun bien cada como con contra cual cuales
    cuando de del desde donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estan estar estas
    este esto estos fue fuera ha hace hacer hay la las le les lo los mas me mi mis mucho muy nada ni no nos o os
    otra otro para pero poco por porque puede pueden que quien se sea ser si sin sobre solo son su sus tambien
    te tiene tienen todo todos tu tus un una unas uno unos usted y ya yo voy vamos quiero necesito puedo tengo
    debo hago saber
    """.split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def stem(token: str) -> str:
    """Stemming mínimo para español: unifica plural y género ("visados", "visado" → "visad")."""
    if len(token) > 4 and token.endswith("es"):
        token = token[:-2]
    elif len(token) > 4 and token.endswith("s"):
        token = token[:-1]
    if len(token) > 4 and token[-1] in "aeo":
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    # Las siglas en mayúsculas se conservan aunque coincidan con una palabra vacía ("ESTA", "ETA").
    acronyms = {strip_accents(a) for a in re.findall(r"\b[A-ZÁÉÍÓÚÑ]{3,}\b", text)}
    return [stem(t) for t in _TOKEN.findall(strip_accents(text)) if (t not in STOPWORDS or t in acronyms) and len(t) > 1]


# Expansión de consulta con vocabulario del dominio: el viajero pregunta "¿cómo me muevo?" o
# "¿dónde duermo?" y las guías dicen "Cómo moverse" o "Dónde alojarse". BM25 solo compara palabras,
# así que se añaden los términos de la sección correspondiente. (Con Claude, el propio modelo
# reescribe la consulta al llamar a la herramienta; con embeddings de Voyage, la similitud
# semántica cubre los sinónimos. Esto ayuda sobre todo al modo demo y al embedder local.)
QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "documentacion entrada visado pasaporte": (
        "papel",
        "papeleo",
        "visado",
        "visa",
        "pasaporte",
        "dni",
        "entrar",
        "entrada",
        "requisito",
        "frontera",
        "documentacion",
        "documento",
        "autorizacion",
        "aduana",
        "inmigracion",
    ),
    "dinero propinas moneda tarjeta efectivo": (
        "dinero",
        "pagar",
        "pago",
        "efectivo",
        "cajero",
        "moneda",
        "cambiar",
        "cambio",
        "tarjeta",
        "propina",
        "caro",
        "precio",
        "regatear",
        "regateo",
    ),
    "como moverse transporte metro aeropuerto": (
        "muevo",
        "moverme",
        "moverse",
        "mover",
        "desplazarme",
        "desplazarse",
        "transporte",
        "metro",
        "autobus",
        "bus",
        "taxi",
        "tren",
        "aeropuerto",
        "llegar",
        "coche",
        "conducir",
        "bici",
        "uber",
    ),
    "seguridad seguro robo": (
        "seguro",
        "segura",
        "seguridad",
        "peligro",
        "peligroso",
        "peligrosa",
        "robo",
        "robar",
        "ladron",
        "timo",
        "estafa",
        "carterista",
        "riesgo",
    ),
    "donde alojarse barrio": (
        "dormir",
        "duermo",
        "alojarme",
        "alojarse",
        "alojamiento",
        "hotel",
        "hospedarme",
        "quedarme",
        "barrio",
        "zona",
        "riad",
        "ryokan",
    ),
    "enchufes conectividad adaptador": (
        "enchufe",
        "adaptador",
        "voltaje",
        "cargador",
        "corriente",
        "electricidad",
        "internet",
        "sim",
        "esim",
        "wifi",
        "datos",
        "roaming",
        "movil",
    ),
    "salud agua grifo": ("agua", "grifo", "beber", "salud", "vacuna", "medico", "hospital", "altitud", "enfermo"),
    "costumbres etiqueta": (
        "costumbre",
        "etiqueta",
        "vestir",
        "ropa",
        "respeto",
        "norma",
        "educado",
        "visto",
        "zapato",
        "foto",
        "fotografiar",
    ),
}
_TRIGGERS = {stem(t): expansion for expansion, triggers in QUERY_EXPANSIONS.items() for t in triggers}


def expand_query(query: str) -> tuple[str, list[str]]:
    """Devuelve la consulta ampliada y los términos añadidos (para mostrarlos en la traza)."""
    added: list[str] = []
    for token in tokenize(query):
        expansion = _TRIGGERS.get(token)
        if expansion and expansion not in added:
            added.append(expansion)
    return (query + " " + " ".join(added)).strip(), added
