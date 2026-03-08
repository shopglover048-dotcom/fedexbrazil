import os
import sqlite3
import secrets
import ipaddress
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, session, url_for, flash, has_request_context

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "novaparcel.db"

STATUS_META = {
    "label-created": {"label_key": "status.label-created", "default_label": "Label Created", "progress": 10},
    "picked-up": {"label_key": "status.picked-up", "default_label": "Picked Up", "progress": 25},
    "in-transit": {"label_key": "status.in-transit", "default_label": "In Transit", "progress": 55},
    "arrived-hub": {"label_key": "status.arrived-hub", "default_label": "Arrived at Hub", "progress": 72},
    "out-for-delivery": {"label_key": "status.out-for-delivery", "default_label": "Out for Delivery", "progress": 90},
    "delivered": {"label_key": "status.delivered", "default_label": "Delivered", "progress": 100},
    "exception": {"label_key": "status.exception", "default_label": "Delivery Exception", "progress": 65},
}

SERVICE_ETA_DAYS = {
    "same-day": 0,
    "express": 1,
    "standard": 3,
    "international": 7,
}

SUPPORTED_LANGUAGES = ("en", "es", "fr", "de", "pt", "ar", "zh")

COUNTRY_LANGUAGE_MAP = {
    "US": "en",
    "GB": "en",
    "CA": "en",
    "AU": "en",
    "NZ": "en",
    "IE": "en",
    "ES": "es",
    "MX": "es",
    "AR": "es",
    "CO": "es",
    "CL": "es",
    "PE": "es",
    "VE": "es",
    "FR": "fr",
    "BE": "fr",
    "CH": "fr",
    "DE": "de",
    "AT": "de",
    "PT": "pt",
    "BR": "pt",
    "AO": "pt",
    "MZ": "pt",
    "AE": "ar",
    "SA": "ar",
    "EG": "ar",
    "MA": "ar",
    "DZ": "ar",
    "QA": "ar",
    "KW": "ar",
    "CN": "zh",
    "TW": "zh",
    "HK": "zh",
    "SG": "zh",
}

TRANSLATIONS = {
    "en": {},
    "es": {
        "nav.home": "Inicio",
        "nav.ship": "Enviar ahora",
        "nav.map": "Mapa en vivo",
        "nav.admin": "Admin",
        "btn.logout": "Cerrar sesion",
        "btn.admin_portal": "Portal admin",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "Envios, seguimiento y operaciones de administrador",
        "status.label-created": "Etiqueta creada",
        "status.picked-up": "Recogido",
        "status.in-transit": "En transito",
        "status.arrived-hub": "Llegado al centro",
        "status.out-for-delivery": "En reparto",
        "status.delivered": "Entregado",
        "status.exception": "Incidencia de entrega",
    },
    "fr": {
        "nav.home": "Accueil",
        "nav.ship": "Expedier",
        "nav.map": "Carte en direct",
        "nav.admin": "Admin",
        "btn.logout": "Se deconnecter",
        "btn.admin_portal": "Portail admin",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "Expedition, suivi et operations administrateur",
        "status.label-created": "Etiquette creee",
        "status.picked-up": "Recupere",
        "status.in-transit": "En transit",
        "status.arrived-hub": "Arrive au hub",
        "status.out-for-delivery": "En cours de livraison",
        "status.delivered": "Livre",
        "status.exception": "Exception de livraison",
    },
    "de": {
        "nav.home": "Startseite",
        "nav.ship": "Jetzt versenden",
        "nav.map": "Live-Karte",
        "nav.admin": "Admin",
        "btn.logout": "Abmelden",
        "btn.admin_portal": "Admin-Portal",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "Versand, Sendungsverfolgung und Admin-Betrieb",
        "status.label-created": "Label erstellt",
        "status.picked-up": "Abgeholt",
        "status.in-transit": "Im Transit",
        "status.arrived-hub": "Im Hub angekommen",
        "status.out-for-delivery": "In Zustellung",
        "status.delivered": "Zugestellt",
        "status.exception": "Lieferausnahme",
    },
    "pt": {
        "nav.home": "Inicio",
        "nav.ship": "Enviar agora",
        "nav.map": "Mapa ao vivo",
        "nav.admin": "Admin",
        "btn.logout": "Sair",
        "btn.admin_portal": "Portal admin",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "Envio, rastreamento e operacoes admin",
        "status.label-created": "Etiqueta criada",
        "status.picked-up": "Coletado",
        "status.in-transit": "Em transito",
        "status.arrived-hub": "Chegou ao hub",
        "status.out-for-delivery": "Saiu para entrega",
        "status.delivered": "Entregue",
        "status.exception": "Excecao de entrega",
    },
    "ar": {
        "nav.home": "الرئيسية",
        "nav.ship": "اشحن الآن",
        "nav.map": "الخريطة المباشرة",
        "nav.admin": "المشرف",
        "btn.logout": "تسجيل الخروج",
        "btn.admin_portal": "بوابة المشرف",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "الشحن والتتبع وعمليات المشرف",
        "status.label-created": "تم إنشاء الملصق",
        "status.picked-up": "تم الاستلام",
        "status.in-transit": "قيد النقل",
        "status.arrived-hub": "وصل إلى المركز",
        "status.out-for-delivery": "خرج للتسليم",
        "status.delivered": "تم التسليم",
        "status.exception": "استثناء في التسليم",
    },
    "zh": {
        "nav.home": "主页",
        "nav.ship": "立即发货",
        "nav.map": "实时地图",
        "nav.admin": "管理",
        "btn.logout": "退出登录",
        "btn.admin_portal": "管理门户",
        "footer.copy": "© 2026 FedEx Logistics",
        "footer.desc": "运输、追踪与管理后台",
        "status.label-created": "已创建面单",
        "status.picked-up": "已揽收",
        "status.in-transit": "运输中",
        "status.arrived-hub": "已到达中转中心",
        "status.out-for-delivery": "派送中",
        "status.delivered": "已送达",
        "status.exception": "配送异常",
    },
}

IN_CLOUD_RUN = bool(os.environ.get("K_SERVICE"))
DEFAULT_BACKEND = "firestore" if IN_CLOUD_RUN else "sqlite"
DATA_BACKEND = os.environ.get("DATA_BACKEND", DEFAULT_BACKEND).strip().lower()

if DATA_BACKEND not in {"sqlite", "firestore"}:
    raise RuntimeError("DATA_BACKEND must be either 'sqlite' or 'firestore'.")

if DATA_BACKEND == "firestore" and firestore is None:
    raise RuntimeError("google-cloud-firestore is required when DATA_BACKEND=firestore.")


def require_env(name: str, fallback: str | None = None) -> str:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    if fallback is not None and not IN_CLOUD_RUN:
        return fallback
    raise RuntimeError(f"Missing required environment variable: {name}")


app = Flask(__name__)
app.config["SECRET_KEY"] = require_env("SECRET_KEY", fallback="dev-secret-change-me")
app.config["ADMIN_USERNAME"] = require_env("ADMIN_USERNAME", fallback="admin")
app.config["ADMIN_PASSWORD"] = require_env("ADMIN_PASSWORD", fallback="ChangeThisPasswordNow!")


def get_db() -> sqlite3.Connection:
    if DATA_BACKEND != "sqlite":
        raise RuntimeError("get_db() is only available for sqlite backend.")
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def get_firestore_client():
    if "firestore_client" not in g:
        g.firestore_client = firestore.Client()
    return g.firestore_client


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()
    g.pop("firestore_client", None)


def init_db() -> None:
    if DATA_BACKEND != "sqlite":
        return
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id TEXT NOT NULL UNIQUE,
            sender_name TEXT NOT NULL,
            sender_email TEXT,
            sender_phone TEXT,
            origin_label TEXT NOT NULL,
            origin_lat REAL NOT NULL,
            origin_lng REAL NOT NULL,
            receiver_name TEXT NOT NULL,
            receiver_email TEXT,
            receiver_phone TEXT,
            destination_label TEXT NOT NULL,
            destination_lat REAL NOT NULL,
            destination_lng REAL NOT NULL,
            package_description TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            service_level TEXT NOT NULL,
            status TEXT NOT NULL,
            eta_utc TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            location_label TEXT NOT NULL,
            note TEXT NOT NULL,
            event_time_utc TEXT NOT NULL,
            FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_events_shipment ON tracking_events(shipment_id);
        """
    )
    db.commit()
    db.close()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("portal_admin_login"))
        return fn(*args, **kwargs)

    return wrapped


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def parse_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")


def tracking_id_exists(tracking_id: str) -> bool:
    if DATA_BACKEND == "firestore":
        client = get_firestore_client()
        return client.collection("shipments").document(tracking_id).get().exists

    db = get_db()
    exists = db.execute("SELECT 1 FROM shipments WHERE tracking_id = ?", (tracking_id,)).fetchone()
    return bool(exists)


def generate_tracking_id() -> str:
    date_part = utc_now().strftime("%y%m%d")
    for _ in range(20):
        random_part = secrets.token_hex(4).upper()
        tracking_id = f"FDX-{date_part}-{random_part}"
        if not tracking_id_exists(tracking_id):
            return tracking_id
    raise RuntimeError("Could not generate unique tracking ID.")


def make_eta(service_level: str) -> str:
    days = SERVICE_ETA_DAYS.get(service_level, 3)
    eta = utc_now() + timedelta(days=days)
    if service_level == "same-day":
        eta = utc_now() + timedelta(hours=6)
    return iso(eta)


def status_label(status_key: str) -> str:
    meta = STATUS_META.get(status_key)
    if not meta:
        return status_key
    return translate_key(get_current_language(), meta["label_key"], meta["default_label"])


def normalize_lang(value: str) -> str:
    if not value:
        return ""
    primary = value.split(",")[0].strip().replace("_", "-").split("-")[0].lower()
    return primary


def detect_country() -> str:
    cached_country = session.get("country", "").strip().upper()
    if len(cached_country) == 2 and cached_country not in {"XX", "ZZ"}:
        return cached_country

    country_headers = ("CF-IPCountry", "X-Country-Code", "X-AppEngine-Country", "CloudFront-Viewer-Country")
    for header in country_headers:
        value = request.headers.get(header, "").strip().upper()
        if len(value) == 2 and value not in {"XX", "ZZ"}:
            session["country"] = value
            return value

    client_ip = detect_client_ip()
    if client_ip:
        detected = detect_country_from_ip(client_ip)
        if detected:
            session["country"] = detected
            return detected
    return ""


def detect_client_ip() -> str:
    ip_headers = ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For")
    for header in ip_headers:
        value = request.headers.get(header, "").strip()
        if not value:
            continue
        candidate = value.split(",")[0].strip()
        if is_public_ip(candidate):
            return candidate

    remote = (request.remote_addr or "").strip()
    if is_public_ip(remote):
        return remote
    return ""


def is_public_ip(candidate: str) -> bool:
    if not candidate:
        return False
    try:
        ip_obj = ipaddress.ip_address(candidate)
        return not (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    except ValueError:
        return False


def detect_country_from_ip(client_ip: str) -> str:
    url = f"https://ipapi.co/{client_ip}/country/"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            raw = response.read().decode("utf-8", errors="ignore").strip().upper()
            if len(raw) == 2 and raw not in {"XX", "ZZ"}:
                return raw
    except Exception:
        return ""
    return ""


def detect_language(country_code: str) -> str:
    forced = normalize_lang(request.args.get("lang", ""))
    if forced in SUPPORTED_LANGUAGES:
        session["lang"] = forced
        return forced

    saved = normalize_lang(session.get("lang", ""))
    if saved in SUPPORTED_LANGUAGES:
        return saved

    mapped = COUNTRY_LANGUAGE_MAP.get(country_code, "")
    if mapped in SUPPORTED_LANGUAGES:
        session["lang"] = mapped
        return mapped

    browser_best = normalize_lang(request.accept_languages.best_match(SUPPORTED_LANGUAGES) or "")
    if browser_best in SUPPORTED_LANGUAGES:
        session["lang"] = browser_best
        return browser_best

    session["lang"] = "en"
    return "en"


def get_current_language() -> str:
    if not has_request_context():
        return "en"
    lang = getattr(g, "lang", "")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def translate_key(lang: str, key: str, default: str = "") -> str:
    localized = TRANSLATIONS.get(lang, {}).get(key)
    if localized:
        return localized
    fallback = TRANSLATIONS["en"].get(key)
    if fallback:
        return fallback
    return default or key


def localized_status_meta(lang: str) -> dict:
    localized = {}
    for status_key, meta in STATUS_META.items():
        localized[status_key] = {
            "label": translate_key(lang, meta["label_key"], meta["default_label"]),
            "progress": meta["progress"],
        }
    return localized


@app.before_request
def set_geo_locale():
    g.country = detect_country()
    g.lang = detect_language(g.country)


def create_shipment(payload: dict, created_by: str) -> str:
    tracking_id = generate_tracking_id()
    now = iso(utc_now())
    eta = make_eta(payload["service_level"])

    if DATA_BACKEND == "firestore":
        client = get_firestore_client()
        shipment = {
            "tracking_id": tracking_id,
            "sender_name": payload["sender_name"],
            "sender_email": payload.get("sender_email", ""),
            "sender_phone": payload.get("sender_phone", ""),
            "origin_label": payload["origin_label"],
            "origin_lat": payload["origin_lat"],
            "origin_lng": payload["origin_lng"],
            "receiver_name": payload["receiver_name"],
            "receiver_email": payload.get("receiver_email", ""),
            "receiver_phone": payload.get("receiver_phone", ""),
            "destination_label": payload["destination_label"],
            "destination_lat": payload["destination_lat"],
            "destination_lng": payload["destination_lng"],
            "package_description": payload["package_description"],
            "weight_kg": payload["weight_kg"],
            "service_level": payload["service_level"],
            "status": "label-created",
            "eta_utc": eta,
            "created_by": created_by,
            "created_at_utc": now,
            "updated_at_utc": now,
        }
        shipment_ref = client.collection("shipments").document(tracking_id)
        shipment_ref.set(shipment)
        event_id = f"{now}-{secrets.token_hex(2)}"
        shipment_ref.collection("events").document(event_id).set(
            {
                "status": "label-created",
                "location_label": payload["origin_label"],
                "note": "Shipment registered and label generated.",
                "event_time_utc": now,
            }
        )
    else:
        db = get_db()
        cur = db.execute(
            """
            INSERT INTO shipments (
                tracking_id, sender_name, sender_email, sender_phone,
                origin_label, origin_lat, origin_lng,
                receiver_name, receiver_email, receiver_phone,
                destination_label, destination_lat, destination_lng,
                package_description, weight_kg, service_level,
                status, eta_utc, created_by, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tracking_id,
                payload["sender_name"],
                payload.get("sender_email", ""),
                payload.get("sender_phone", ""),
                payload["origin_label"],
                payload["origin_lat"],
                payload["origin_lng"],
                payload["receiver_name"],
                payload.get("receiver_email", ""),
                payload.get("receiver_phone", ""),
                payload["destination_label"],
                payload["destination_lat"],
                payload["destination_lng"],
                payload["package_description"],
                payload["weight_kg"],
                payload["service_level"],
                "label-created",
                eta,
                created_by,
                now,
                now,
            ),
        )
        shipment_id = cur.lastrowid

        db.execute(
            """
            INSERT INTO tracking_events (shipment_id, status, location_label, note, event_time_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                shipment_id,
                "label-created",
                payload["origin_label"],
                "Shipment registered and label generated.",
                now,
            ),
        )
        db.commit()
    return tracking_id


def load_shipment_with_events(tracking_id: str):
    normalized_id = tracking_id.upper()
    if DATA_BACKEND == "firestore":
        client = get_firestore_client()
        shipment_doc = client.collection("shipments").document(normalized_id).get()
        if not shipment_doc.exists:
            return None, []
        shipment = shipment_doc.to_dict() or {}
        shipment["tracking_id"] = normalized_id
        event_docs = (
            client.collection("shipments")
            .document(normalized_id)
            .collection("events")
            .order_by("event_time_utc", direction=firestore.Query.DESCENDING)
            .stream()
        )
        events = [doc.to_dict() for doc in event_docs]
        return shipment, events

    db = get_db()
    shipment = db.execute("SELECT * FROM shipments WHERE tracking_id = ?", (normalized_id,)).fetchone()
    if not shipment:
        return None, []
    events = db.execute(
        """
        SELECT * FROM tracking_events
        WHERE shipment_id = ?
        ORDER BY event_time_utc DESC, id DESC
        """,
        (shipment["id"],),
    ).fetchall()
    return shipment, events


def extract_payload(form) -> dict:
    payload = {
        "sender_name": form.get("sender_name", "").strip(),
        "sender_email": form.get("sender_email", "").strip(),
        "sender_phone": form.get("sender_phone", "").strip(),
        "origin_label": form.get("origin_label", "").strip(),
        "origin_lat": parse_float(form.get("origin_lat", ""), "Origin latitude"),
        "origin_lng": parse_float(form.get("origin_lng", ""), "Origin longitude"),
        "receiver_name": form.get("receiver_name", "").strip(),
        "receiver_email": form.get("receiver_email", "").strip(),
        "receiver_phone": form.get("receiver_phone", "").strip(),
        "destination_label": form.get("destination_label", "").strip(),
        "destination_lat": parse_float(form.get("destination_lat", ""), "Destination latitude"),
        "destination_lng": parse_float(form.get("destination_lng", ""), "Destination longitude"),
        "package_description": form.get("package_description", "").strip(),
        "weight_kg": parse_float(form.get("weight_kg", ""), "Weight"),
        "service_level": form.get("service_level", "standard").strip(),
    }

    required = [
        "sender_name",
        "origin_label",
        "receiver_name",
        "destination_label",
        "package_description",
    ]
    for key in required:
        if not payload[key]:
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")
    if payload["service_level"] not in SERVICE_ETA_DAYS:
        raise ValueError("Service level is invalid.")
    if payload["weight_kg"] <= 0:
        raise ValueError("Weight must be greater than 0.")

    return payload


@app.context_processor
def inject_globals():
    lang = get_current_language()
    return {
        "status_meta": localized_status_meta(lang),
        "current_lang": lang,
        "current_country": getattr(g, "country", ""),
        "t": lambda key, default="": translate_key(lang, key, default),
        "supported_languages": SUPPORTED_LANGUAGES,
    }


@app.get("/")
def home():
    return render_template("home.html")


@app.get("/world-map")
def world_map():
    return render_template("world_map.html")


@app.get("/portal")
def admin_portal():
    return render_template("admin_portal.html")


@app.post("/track")
def track_lookup():
    tracking_id = request.form.get("tracking_id", "").strip().upper()
    if not tracking_id:
        flash("Tracking number is required.", "error")
        return redirect(url_for("home"))
    return redirect(url_for("track_page", tracking_id=tracking_id))


@app.get("/ship")
def ship_page():
    return render_template("ship.html")


@app.post("/ship")
def ship_submit():
    try:
        payload = extract_payload(request.form)
        tracking_id = create_shipment(payload, created_by="user")
        flash(f"Shipment created. Tracking ID: {tracking_id}", "success")
        return redirect(url_for("track_page", tracking_id=tracking_id))
    except ValueError as exc:
        flash(str(exc), "error")
    except RuntimeError as exc:
        flash(str(exc), "error")
    return redirect(url_for("ship_page"))


@app.get("/track/<tracking_id>")
def track_page(tracking_id: str):
    shipment, events = load_shipment_with_events(tracking_id)
    if not shipment:
        return render_template("track_not_found.html", tracking_id=tracking_id.upper()), 404

    progress = STATUS_META.get(shipment["status"], {"progress": 0})["progress"]
    return render_template(
        "track.html",
        shipment=shipment,
        events=events,
        progress=progress,
        status_label=status_label(shipment["status"]),
    )


@app.get("/admin/login")
def admin_login():
    return redirect(url_for("portal_admin_login"))


@app.get("/portal/admin-login")
def portal_admin_login():
    return render_template("admin_login.html")


@app.post("/admin/login")
def admin_login_submit():
    return admin_login_submit_portal()


@app.post("/portal/admin-login")
def admin_login_submit_portal():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    valid_user = secrets.compare_digest(username, app.config["ADMIN_USERNAME"])
    valid_pass = secrets.compare_digest(password, app.config["ADMIN_PASSWORD"])

    if valid_user and valid_pass:
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))

    flash("Invalid admin credentials.", "error")
    return redirect(url_for("portal_admin_login"))


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin session closed.", "success")
    return redirect(url_for("home"))


@app.get("/admin")
@login_required
def admin_dashboard():
    if DATA_BACKEND == "firestore":
        client = get_firestore_client()
        docs = (
            client.collection("shipments")
            .order_by("created_at_utc", direction=firestore.Query.DESCENDING)
            .limit(150)
            .stream()
        )
        shipments = [doc.to_dict() for doc in docs]
    else:
        db = get_db()
        shipments = db.execute(
            """
            SELECT tracking_id, sender_name, receiver_name, origin_label, destination_label,
                   status, created_at_utc, updated_at_utc
            FROM shipments
            ORDER BY id DESC
            LIMIT 150
            """
        ).fetchall()
    return render_template("admin_dashboard.html", shipments=shipments)


@app.post("/admin/create")
@login_required
def admin_create_shipment():
    try:
        payload = extract_payload(request.form)
        tracking_id = create_shipment(payload, created_by="admin")
        flash(f"Shipment created by operations team. Tracking ID: {tracking_id}", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except RuntimeError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/update-status")
@login_required
def admin_update_status():
    tracking_id = request.form.get("tracking_id", "").strip().upper()
    new_status = request.form.get("status", "").strip()
    location_label = request.form.get("location_label", "").strip()
    note = request.form.get("note", "").strip()

    if new_status not in STATUS_META:
        flash("Invalid status selected.", "error")
        return redirect(url_for("admin_dashboard"))

    shipment, _ = load_shipment_with_events(tracking_id)
    if not shipment:
        flash("Tracking ID not found.", "error")
        return redirect(url_for("admin_dashboard"))

    if not location_label:
        location_label = shipment["destination_label"] if new_status == "delivered" else shipment["origin_label"]
    if not note:
        note = f"Status changed to {translate_key('en', STATUS_META[new_status]['label_key'], STATUS_META[new_status]['default_label'])} by operations team."

    now = iso(utc_now())
    if DATA_BACKEND == "firestore":
        client = get_firestore_client()
        shipment_ref = client.collection("shipments").document(tracking_id)
        shipment_ref.update({"status": new_status, "updated_at_utc": now})
        event_id = f"{now}-{secrets.token_hex(2)}"
        shipment_ref.collection("events").document(event_id).set(
            {
                "status": new_status,
                "location_label": location_label,
                "note": note,
                "event_time_utc": now,
            }
        )
    else:
        db = get_db()
        db.execute(
            "UPDATE shipments SET status = ?, updated_at_utc = ? WHERE id = ?",
            (new_status, now, shipment["id"]),
        )
        db.execute(
            """
            INSERT INTO tracking_events (shipment_id, status, location_label, note, event_time_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (shipment["id"], new_status, location_label, note, now),
        )
        db.commit()

    flash(f"{tracking_id} updated to {status_label(new_status)}.", "success")
    return redirect(url_for("admin_dashboard"))


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=port)






