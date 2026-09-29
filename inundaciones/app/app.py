import os
import re
import time
import functools
from datetime import datetime, timedelta, timezone

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

from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)


# ============================================================
# BASE DE DATOS
# ============================================================

def query(sql, params=(), one=False, commit=False):

    con = mysql.connector.connect(
        host=os.getenv("DB_HOST", "db"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"]
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

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

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

            session.clear()

            session.update(
                uid=u["id"],
                rol=u["rol"],
                nombre=u["nombre"]
            )

            return redirect(
                url_for("mapa")
            )

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

@app.route("/logout")
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

    bid = (
        request
        .get_json(silent=True)
        or {}
    ).get("barrio_id")

    if not query(
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

    query(
        """
        INSERT INTO historial_inundaciones
        (barrio_id, fecha, descripcion)
        VALUES (%s, %s, %s)
        """,
        (
            j.get("barrio_id"),
            j.get("fecha"),
            j.get("descripcion", "")[:255]
        ),
        commit=True
    )

    return jsonify(
        ok=True
    ), 201


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
