import os
import re
import hmac
import time
import secrets
import smtplib
import functools
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

import click
import mysql.connector
import requests

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    abort
)

from werkzeug.exceptions import HTTPException

from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # En producción (HTTPS) poner SESSION_COOKIE_SECURE=true en el .env.
    # Por defecto queda en false para poder probar en http://localhost.
    SESSION_COOKIE_SECURE=(
        os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    ),
    MAX_CONTENT_LENGTH=16 * 1024
)


# ============================================================
# SEGURIDAD: CSRF, CABECERAS Y ERRORES
# ============================================================

def csrf_token():

    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)

    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def verificar_csrf():

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):

        enviado = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("_csrf", "")
        )

        esperado = session.get("_csrf", "")

        if not esperado or not hmac.compare_digest(enviado, esperado):
            abort(400, "csrf")


@app.after_request
def cabeceras(resp):

    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")

    return resp


MENSAJES = {
    400: "La solicitud no es válida o la sesión venció. Recargá la página e intentá de nuevo.",
    403: "No tenés permiso para hacer esto.",
    404: "No encontramos lo que buscabas.",
    405: "Esa acción no está permitida desde acá.",
    413: "El envío es demasiado grande.",
    429: "Demasiados intentos. Esperá unos minutos e intentá de nuevo.",
    502: "No pudimos consultar un servicio externo.",
    503: "El servicio no está disponible en este momento. Probá de nuevo en unos minutos."
}


def responder_error(codigo, mensaje=None):

    mensaje = mensaje or MENSAJES.get(codigo, "Ocurrió un error inesperado.")

    if request.path.startswith("/api/"):
        return jsonify(error=mensaje), codigo

    return render_template(
        "error.html",
        codigo=codigo,
        mensaje=mensaje
    ), codigo


@app.errorhandler(HTTPException)
def error_http(e):
    return responder_error(e.code)


@app.errorhandler(mysql.connector.Error)
def error_bd(e):

    app.logger.error("Error de base de datos: %s", e)

    return responder_error(503)


@app.errorhandler(500)
def error_interno(e):
    return responder_error(500)


def a_entero(v):

    if isinstance(v, bool):
        return None

    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ============================================================
# BASE DE DATOS
# ============================================================

def query(sql, params=(), one=False, commit=False):

    con = mysql.connector.connect(
        host=os.getenv("DB_HOST", "db"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        connection_timeout=5
    )

    cur = con.cursor(dictionary=True)

    try:

        cur.execute(sql, params)

        if commit:
            con.commit()
            return cur.lastrowid

        rows = cur.fetchall()

        return (
            rows[0] if rows else None
        ) if one else rows

    finally:

        cur.close()
        con.close()


# ============================================================
# CLIMA
# ============================================================

_cache = {}


def clima_open_meteo(lat, lon):

    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        timeout=8,
        params={
            "latitude": lat,
            "longitude": lon,
            "past_days": 3,
            "forecast_days": 3,
            "daily": "precipitation_sum,precipitation_probability_max",
            "timezone": "America/Montevideo"
        }
    )

    r.raise_for_status()

    d = r.json()["daily"]

    mm = [
        x or 0
        for x in d["precipitation_sum"]
    ]

    pr = [
        x or 0
        for x in d["precipitation_probability_max"]
    ]

    return {
        "pasada_mm": mm[:3],
        "pronostico_mm": mm[3:],
        "prob_max": pr[3:]
    }


# ============================================================
# INUMET
# ============================================================

INUMET = "https://w2b.inumet.gub.uy/oapi"

COLECCION_OBS = (
    "urn:wmo:md:uy-inumet:"
    "surface-based-observations.synop"
)

# Verificar en la documentación de INUMET
# el nombre exacto de la variable y su período.
VARIABLE_LLUVIA = os.getenv(
    "INUMET_VARIABLE_LLUVIA",
    "total_precipitation"
)

_estac = {
    "t": 0,
    "lista": []
}


def _inumet(path, **params):

    r = requests.get(
        INUMET + path,
        params={
            "f": "json",
            **params
        },
        timeout=10
    )

    r.raise_for_status()

    return r.json()


def estaciones():

    if time.time() - _estac["t"] > 86400:

        fs = _inumet(
            "/collections/stations/items",
            limit=200
        )["features"]

        _estac.update(
            t=time.time(),
            lista=[
                (
                    f["id"],
                    f["geometry"]["coordinates"][1],
                    f["geometry"]["coordinates"][0]
                )

                for f in fs

                if f.get("geometry")
            ]
        )

    return _estac["lista"]


def lluvia_observada(lat, lon):

    """
    Obtiene los mm de lluvia observados
    durante los últimos 3 días en la estación
    de INUMET más cercana.
    """

    est = min(
        estaciones(),
        key=lambda e:
            (e[1] - float(lat)) ** 2 +
            (e[2] - float(lon)) ** 2
    )[0]

    desde = (
        datetime.now(timezone.utc)
        - timedelta(days=3)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    fs = _inumet(
        f"/collections/{COLECCION_OBS}/items",
        wigos_station_identifier=est,
        name=VARIABLE_LLUVIA,
        datetime=f"{desde}/..",
        limit=500
    )["features"]

    return sum(
        float(
            f["properties"]["value"] or 0
        )
        for f in fs
    )


def clima_inumet(lat, lon):

    # El pronóstico sigue viniendo de Open-Meteo.
    datos = clima_open_meteo(lat, lon)

    try:

        datos["pasada_mm"] = [
            lluvia_observada(lat, lon)
        ]

    except Exception:

        app.logger.warning(
            "INUMET falló; uso la lluvia pasada de Open-Meteo",
            exc_info=True
        )

    return datos


def clima(lat, lon):

    key = (
        round(float(lat), 2),
        round(float(lon), 2)
    )

    hit = _cache.get(key)

    # Caché de 30 minutos
    if hit and time.time() - hit[0] < 1800:
        return hit[1]

    if os.getenv("PROVEEDOR_CLIMA") == "inumet":
        fuente = clima_inumet
    else:
        fuente = clima_open_meteo

    datos = fuente(*key)

    _cache[key] = (
        time.time(),
        datos
    )

    return datos


# ============================================================
# RIESGO
# ============================================================

NIVELES = [
    (0.25, "Bajo", "#2e9e5b"),
    (0.50, "Medio", "#e8c22f"),
    (0.75, "Alto", "#e8801f"),
    (1.01, "Muy alto", "#c62d2d")
]


def factor_terreno(b):

    if (
        b["altitud_m"] is None
        or b["dist_agua_m"] is None
    ):
        # Sin datos de terreno: valor neutro
        return 0.5

    bajo = 1 - min(
        b["altitud_m"] / 50,
        1
    )

    cerca = 1 - min(
        b["dist_agua_m"] / 2000,
        1
    )

    return (
        0.6 * bajo
        + 0.4 * cerca
    )


def calcular_riesgo(c, b):

    lluvia = min(
        (
            0.4 * sum(c["pasada_mm"])
            +
            0.6 * sum(c["pronostico_mm"])
        ) / 100,
        1
    )

    prob = (
        max(c["prob_max"] or [0])
        / 100
    )

    p = (
        0.55 * lluvia
        +
        0.15 * prob
        +
        0.30 * factor_terreno(b)
    )

    nivel, color = next(
        (
            (n, col)
            for lim, n, col in NIVELES
            if p < lim
        )
    )

    return {
        "probabilidad": round(p * 100),
        "nivel": nivel,
        "color": color
    }


# ============================================================
# AUTENTICACIÓN
# ============================================================

def login_required(f):

    @functools.wraps(f)
    def w(*a, **k):

        if "uid" not in session:
            return redirect(
                url_for("login")
            )

        return f(*a, **k)

    return w


def admin_required(f):

    @login_required
    @functools.wraps(f)
    def w(*a, **k):

        if session.get("rol") != "admin":
            abort(403)

        return f(*a, **k)

    return w


# ============================================================
# REGISTRO
# ============================================================

@app.route(
    "/registro",
    methods=["GET", "POST"]
)
def registro():

    if request.method == "POST":

        nombre, email, pw = (
            request.form.get(k, "").strip()
            for k in (
                "nombre",
                "email",
                "password"
            )
        )

        if (
            not nombre
            or not re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+",
                email
            )
            or len(pw) < 8
            or len(pw) > 128
            or len(nombre) > 80
            or len(email) > 120
        ):

            flash(
                "Completá tu nombre, un email válido "
                "y una contraseña de al menos 8 caracteres."
            )

        else:

            try:

                query(
                    """
                    INSERT INTO usuarios
                    (nombre, email, password_hash)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        nombre,
                        email.lower(),
                        generate_password_hash(pw)
                    ),
                    commit=True
                )

                flash(
                    "Cuenta creada. Ya podés iniciar sesión."
                )

                return redirect(
                    url_for("login")
                )

            except mysql.connector.IntegrityError:

                flash(
                    "Ya existe una cuenta con ese email."
                )

    return render_template(
        "auth.html",
        registro=True
    )


# ============================================================
# LOGIN
# ============================================================

_intentos = {}

MAX_INTENTOS_EMAIL = 5
MAX_INTENTOS_IP = 30
VENTANA_SEG = 900


def _recientes(clave):

    ahora = time.time()

    lista = [
        t for t in _intentos.get(clave, [])
        if ahora - t < VENTANA_SEG
    ]

    if lista:
        _intentos[clave] = lista
    else:
        _intentos.pop(clave, None)

    return lista


def bloqueado(email, ip):

    return (
        len(_recientes(("email", email))) >= MAX_INTENTOS_EMAIL
        or len(_recientes(("ip", ip))) >= MAX_INTENTOS_IP
    )


def registrar_fallo(email, ip):

    for clave in (("email", email), ("ip", ip)):
        _intentos.setdefault(clave, []).append(time.time())

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        ip = request.remote_addr or "?"

        if bloqueado(email, ip):

            flash(MENSAJES[429])

            return render_template(
                "auth.html",
                registro=False
            ), 429

        u = query(
            """
            SELECT *
            FROM usuarios
            WHERE email=%s
            """,
            (email,),
            one=True
        )

        if (
            u
            and check_password_hash(
                u["password_hash"],
                password
            )
        ):

            _intentos.pop(("email", email), None)

            session.clear()

            session.update(
                uid=u["id"],
                rol=u["rol"],
                nombre=u["nombre"]
            )

            return redirect(
                url_for("mapa")
            )

        registrar_fallo(email, ip)

        flash(
            "Email o contraseña incorrectos."
        )

    return render_template(
        "auth.html",
        registro=False
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# PÁGINA DE INICIO
# ============================================================

@app.route("/")
def inicio():

    return render_template(
        "inicio.html"
    )


# ============================================================
# MAPA
# ============================================================

@app.route("/mapa")
@login_required
def mapa():

    deps = query(
        """
        SELECT id, nombre
        FROM departamentos
        ORDER BY nombre
        """
    )

    zona = query(
        """
        SELECT
            b.id barrio_id,
            b.departamento_id

        FROM usuarios u

        JOIN barrios b
            ON b.id = u.barrio_id

        WHERE u.id=%s
        """,
        (session["uid"],),
        one=True
    )

    return render_template(
        "mapa.html",
        deps=deps,
        zona=zona
    )


# ============================================================
# API DE RIESGO POR DEPARTAMENTO
# ============================================================

@app.route(
    "/api/departamentos/<int:dep_id>/riesgo"
)
@login_required
def riesgo_departamento(dep_id):

    d = query(
        """
        SELECT lat, lon
        FROM departamentos
        WHERE id=%s
        """,
        (dep_id,),
        one=True
    )

    if not d:
        abort(404)

    barrios = query(
        """
        SELECT *
        FROM barrios
        WHERE departamento_id=%s
        ORDER BY nombre
        """,
        (dep_id,)
    )

    try:

        c = clima(
            d["lat"],
            d["lon"]
        )

    except Exception:

        return jsonify(
            error=(
                "No pudimos obtener el pronóstico. "
                "Probá de nuevo en unos minutos."
            )
        ), 502

    out = []

    for b in barrios:

        resultado = calcular_riesgo(
            c,
            b
        )

        out.append(
            {
                "id": b["id"],
                "nombre": b["nombre"],
                "lat": float(b["lat"]),
                "lon": float(b["lon"]),
                "terreno": (
                    b["altitud_m"] is not None
                ),
                **resultado
            }
        )

    return jsonify(
        barrios=out,

        centro=[
            float(d["lat"]),
            float(d["lon"])
        ],

        lluvia_pasada_mm=round(
            sum(c["pasada_mm"])
        ),

        lluvia_prevista_mm=round(
            sum(c["pronostico_mm"])
        )
    )


# ============================================================
# GUARDAR ZONA DEL USUARIO
# ============================================================

@app.route(
    "/api/zona",
    methods=["POST"]
)
@login_required
def guardar_zona():

    bid = a_entero(
        (
            request
            .get_json(silent=True)
            or {}
        ).get("barrio_id")
    )

    if bid is None or not query(
        """
        SELECT id
        FROM barrios
        WHERE id=%s
        """,
        (bid,),
        one=True
    ):

        abort(400)

    query(
        """
        UPDATE usuarios
        SET barrio_id=%s
        WHERE id=%s
        """,
        (
            bid,
            session["uid"]
        ),
        commit=True
    )

    return jsonify(
        ok=True
    )


# ============================================================
# HISTORIAL DE INUNDACIONES
# ============================================================

@app.route(
    "/api/barrios/<int:bid>/historial"
)
@login_required
def historial(bid):

    filas = query(
        """
        SELECT fecha, descripcion
        FROM historial_inundaciones
        WHERE barrio_id=%s
        ORDER BY fecha DESC
        """,
        (bid,)
    )

    return jsonify(
        [
            {
                "fecha": f["fecha"].isoformat(),
                "descripcion": f["descripcion"]
            }

            for f in filas
        ]
    )


# ============================================================
# ADMINISTRACIÓN DEL HISTORIAL
# ============================================================

@app.route(
    "/api/admin/historial",
    methods=["POST"]
)
@admin_required
def admin_historial():

    j = (
        request
        .get_json(silent=True)
        or {}
    )

    bid = a_entero(j.get("barrio_id"))

    if bid is None or not query(
        "SELECT id FROM barrios WHERE id=%s",
        (bid,),
        one=True
    ):
        return jsonify(error="barrio_id inválido."), 400

    try:
        fecha = datetime.strptime(
            str(j.get("fecha", "")),
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return jsonify(error="La fecha debe tener formato AAAA-MM-DD."), 400

    if fecha > datetime.now().date():
        return jsonify(error="La fecha no puede ser futura."), 400

    desc = j.get("descripcion")

    desc = (
        desc.strip()[:255]
        if isinstance(desc, str)
        else ""
    ) or None

    query(
        """
        INSERT INTO historial_inundaciones
        (barrio_id, fecha, descripcion)
        VALUES (%s, %s, %s)
        """,
        (bid, fecha, desc),
        commit=True
    )

    return jsonify(
        ok=True
    ), 201


# ============================================================
# BARRIOS POR DEPARTAMENTO (para los selectores)
# ============================================================

@app.route("/api/departamentos/<int:dep_id>/barrios")
@login_required
def barrios_departamento(dep_id):

    return jsonify(
        query(
            """
            SELECT id, nombre
            FROM barrios
            WHERE departamento_id=%s
            ORDER BY nombre
            """,
            (dep_id,)
        )
    )


# ============================================================
# NOTIFICACIONES DE ALERTA
# ============================================================

ORDEN_NIVEL = ["Bajo", "Medio", "Alto", "Muy alto"]

MAX_SUSCRIPCIONES = 20

# Si el riesgo sigue por encima del umbral, se vuelve a avisar
# recién pasadas estas horas (salvo que el nivel empeore).
REAVISO_HORAS = int(os.getenv("ALERTA_REAVISO_HORAS", "24"))


def enviar_email(destino, asunto, cuerpo):

    """Envía un email por SMTP. Devuelve True si salió."""

    host = os.getenv("SMTP_HOST")

    if not host:
        return False

    usuario = os.getenv("SMTP_USER", "")

    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", usuario or "alertas@innuvora.local")
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    puerto = int(os.getenv("SMTP_PORT", "587"))
    ssl_directo = os.getenv("SMTP_SSL", "false").lower() == "true"
    starttls = os.getenv("SMTP_STARTTLS", "true").lower() == "true"

    try:

        if ssl_directo:
            srv = smtplib.SMTP_SSL(host, puerto, timeout=15)
        else:
            srv = smtplib.SMTP(host, puerto, timeout=15)

        with srv:

            if starttls and not ssl_directo:
                srv.starttls()

            if usuario:
                srv.login(usuario, os.getenv("SMTP_PASSWORD", ""))

            srv.send_message(msg)

        return True

    except Exception:

        app.logger.warning(
            "No se pudo enviar el email a un usuario",
            exc_info=True
        )

        return False


def debe_avisar(s, nivel):

    # Primera vez que supera el umbral (o volvió a superarlo)
    if s["ultimo_nivel"] is None or s["horas_desde"] is None:
        return True

    # El nivel empeoró desde el último aviso
    if ORDEN_NIVEL.index(nivel) > ORDEN_NIVEL.index(s["ultimo_nivel"]):
        return True

    # Sigue alto: recordatorio pasado el período de espera
    return s["horas_desde"] >= REAVISO_HORAS


def enviar_alertas():

    """
    Recorre las suscripciones, calcula el riesgo actual de cada
    barrio y avisa a quien superó su umbral. Devuelve la cantidad
    de notificaciones generadas.
    """

    subs = query(
        """
        SELECT
            s.usuario_id, s.barrio_id, s.umbral, s.ultimo_nivel,
            TIMESTAMPDIFF(HOUR, s.ultimo_aviso, NOW()) AS horas_desde,
            u.email, u.nombre, u.alertas_email,
            b.nombre AS barrio, b.altitud_m, b.dist_agua_m,
            d.id AS dep_id, d.nombre AS departamento,
            d.lat AS dlat, d.lon AS dlon
        FROM suscripciones s
        JOIN usuarios u ON u.id = s.usuario_id
        JOIN barrios b ON b.id = s.barrio_id
        JOIN departamentos d ON d.id = b.departamento_id
        """
    )

    climas = {}
    generadas = 0

    for s in subs:

        if s["dep_id"] not in climas:

            try:
                climas[s["dep_id"]] = clima(s["dlat"], s["dlon"])

            except Exception:

                app.logger.warning(
                    "Sin clima para el departamento %s",
                    s["dep_id"],
                    exc_info=True
                )

                climas[s["dep_id"]] = None

        c = climas[s["dep_id"]]

        if c is None:
            continue

        r = calcular_riesgo(c, s)

        if r["probabilidad"] < s["umbral"]:

            # Bajó del umbral: se "rearma" para el próximo aviso
            if s["ultimo_nivel"] is not None:

                query(
                    """
                    UPDATE suscripciones
                    SET ultimo_nivel=NULL
                    WHERE usuario_id=%s AND barrio_id=%s
                    """,
                    (s["usuario_id"], s["barrio_id"]),
                    commit=True
                )

            continue

        if not debe_avisar(s, r["nivel"]):
            continue

        mensaje = (
            f"Riesgo {r['nivel'].lower()} de inundación en "
            f"{s['barrio']} ({s['departamento']}): "
            f"{r['probabilidad']}% (tu umbral es {s['umbral']}%). "
            f"Lluvia prevista próximos 3 días: "
            f"{round(sum(c['pronostico_mm']))} mm."
        )

        enviado = False

        if s["alertas_email"]:

            base = os.getenv("APP_URL", "").rstrip("/")

            cuerpo = (
                f"Hola {s['nombre']},\n\n{mensaje}\n\n"
                "Es una estimación, no un aviso oficial. "
                "Seguí las indicaciones de las autoridades "
                "y revisá el mapa para más detalle"
                + (f": {base}/mapa" if base else ".")
                + "\n\nPodés cambiar tus alertas desde la sección "
                "Alertas de INNUVORA.\n"
            )

            enviado = enviar_email(
                s["email"],
                f"INNUVORA: riesgo {r['nivel'].lower()} en {s['barrio']}",
                cuerpo
            )

        query(
            """
            INSERT INTO notificaciones
            (usuario_id, barrio_id, probabilidad, nivel,
             mensaje, enviada_email)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                s["usuario_id"], s["barrio_id"],
                r["probabilidad"], r["nivel"],
                mensaje, int(enviado)
            ),
            commit=True
        )

        query(
            """
            UPDATE suscripciones
            SET ultimo_aviso=NOW(), ultimo_nivel=%s
            WHERE usuario_id=%s AND barrio_id=%s
            """,
            (r["nivel"], s["usuario_id"], s["barrio_id"]),
            commit=True
        )

        generadas += 1

    return generadas


def suscribir(uid, bid, umbral):

    """Crea o actualiza una suscripción. Devuelve un error o None."""

    if bid is None or not query(
        "SELECT id FROM barrios WHERE id=%s",
        (bid,),
        one=True
    ):
        return "Elegí un barrio válido."

    if umbral is None or not 10 <= umbral <= 90:
        return "El umbral debe estar entre 10 y 90."

    ya = query(
        """
        SELECT COUNT(*) AS n
        FROM suscripciones
        WHERE usuario_id=%s AND barrio_id<>%s
        """,
        (uid, bid),
        one=True
    )["n"]

    if ya >= MAX_SUSCRIPCIONES:
        return f"Podés seguir hasta {MAX_SUSCRIPCIONES} barrios."

    query(
        """
        INSERT INTO suscripciones (usuario_id, barrio_id, umbral)
        VALUES (%s, %s, %s) AS nuevo
        ON DUPLICATE KEY UPDATE
            umbral = nuevo.umbral,
            ultimo_nivel = NULL
        """,
        (uid, bid, umbral),
        commit=True
    )

    return None


@app.route("/alertas")
@login_required
def alertas():

    uid = session["uid"]

    return render_template(
        "alertas.html",
        deps=query("SELECT id, nombre FROM departamentos ORDER BY nombre"),
        subs=query(
            """
            SELECT s.barrio_id, s.umbral,
                   b.nombre AS barrio, d.nombre AS departamento
            FROM suscripciones s
            JOIN barrios b ON b.id = s.barrio_id
            JOIN departamentos d ON d.id = b.departamento_id
            WHERE s.usuario_id=%s
            ORDER BY d.nombre, b.nombre
            """,
            (uid,)
        ),
        notifs=query(
            """
            SELECT mensaje, nivel, creado, leida
            FROM notificaciones
            WHERE usuario_id=%s
            ORDER BY creado DESC
            LIMIT 20
            """,
            (uid,)
        ),
        email_activo=query(
            "SELECT alertas_email FROM usuarios WHERE id=%s",
            (uid,),
            one=True
        )["alertas_email"],
        smtp=bool(os.getenv("SMTP_HOST"))
    )


@app.route("/alertas/suscribir", methods=["POST"])
@login_required
def alertas_suscribir():

    error = suscribir(
        session["uid"],
        a_entero(request.form.get("barrio_id")),
        a_entero(request.form.get("umbral"))
    )

    flash(error or "Alerta guardada.")

    return redirect(url_for("alertas"))


@app.route("/alertas/eliminar", methods=["POST"])
@login_required
def alertas_eliminar():

    query(
        "DELETE FROM suscripciones WHERE usuario_id=%s AND barrio_id=%s",
        (session["uid"], a_entero(request.form.get("barrio_id"))),
        commit=True
    )

    flash("Alerta eliminada.")

    return redirect(url_for("alertas"))


@app.route("/alertas/preferencias", methods=["POST"])
@login_required
def alertas_preferencias():

    query(
        "UPDATE usuarios SET alertas_email=%s WHERE id=%s",
        (1 if request.form.get("alertas_email") else 0, session["uid"]),
        commit=True
    )

    flash("Preferencias guardadas.")

    return redirect(url_for("alertas"))


@app.route("/alertas/leidas", methods=["POST"])
@login_required
def alertas_leidas():

    query(
        "UPDATE notificaciones SET leida=1 WHERE usuario_id=%s",
        (session["uid"],),
        commit=True
    )

    return redirect(url_for("alertas"))


@app.route("/api/alertas", methods=["POST"])
@login_required
def api_alertas():

    j = request.get_json(silent=True) or {}

    error = suscribir(
        session["uid"],
        a_entero(j.get("barrio_id")),
        a_entero(j.get("umbral", 50))
    )

    if error:
        return jsonify(error=error), 400

    return jsonify(ok=True), 201


@app.route("/api/admin/alertas/enviar", methods=["POST"])
@admin_required
def admin_enviar_alertas():

    return jsonify(generadas=enviar_alertas())


# ============================================================
# COMANDOS DE TERMINAL
# ============================================================

@app.cli.command("enviar-alertas")
def cmd_enviar_alertas():

    """Calcula el riesgo y envía las alertas pendientes."""

    click.echo(f"Alertas generadas: {enviar_alertas()}")


@app.cli.command("crear-admin")
@click.argument("email")
def cmd_crear_admin(email):

    """Da rol de administrador a un usuario ya registrado."""

    email = email.strip().lower()

    if not query(
        "SELECT id FROM usuarios WHERE email=%s",
        (email,),
        one=True
    ):
        raise click.ClickException("Ese email no está registrado.")

    query(
        "UPDATE usuarios SET rol='admin' WHERE email=%s",
        (email,),
        commit=True
    )

    click.echo(f"{email} ahora es administrador.")


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=False
    )
