#!/usr/bin/env python3
"""Prepara el mensaje de asistencia del próximo partido, listo para pegar en WhatsApp,
y opcionalmente lo envía por correo con Gmail.

Lee docs/partidos.json y la tabla de asistencia de Supabase. Solo usa la librería estándar. Uso:
    SUPABASE_URL=... SUPABASE_KEY=... python scripts/resumen.py
    python scripts/resumen.py --now 2026-10-24T08:00      # simular otra fecha
    GMAIL_USER=... GMAIL_APP_PASSWORD=... MAIL_TO=... python scripts/resumen.py --enviar
"""
import argparse
import datetime as dt
import json
import os
import re
import smtplib
import sys
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
# Más allá de esto no es "el partido de este finde"
HORIZONTE = dt.timedelta(days=8)
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def minimo_jugadores():
    """Lee minimoJugadores de docs/config.js para avisar igual que la web."""
    m = re.search(r"minimoJugadores:\s*(\d+)", (DOCS / "config.js").read_text(encoding="utf-8"))
    return int(m.group(1)) if m else 5


def leer_asistencia(partido_id):
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        sys.exit("Faltan SUPABASE_URL y SUPABASE_KEY")
    req = urllib.request.Request(
        f"{url}/rest/v1/asistencia?select=jugador_id,estado&partido_id=eq.{partido_id}",
        headers={"apikey": key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fecha_larga(d):
    """2026-10-25 09:00 -> 'Domingo 25 de octubre · 09:00'"""
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]} · {d:%H:%M}"


def web_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def mensaje(data, ahora):
    """Devuelve (asunto, texto) del correo."""
    proximo = next(
        (p for p in data["partidos"]
         if p["estado"] == "programado" and dt.datetime.fromisoformat(p["inicio"]) >= ahora),
        None,
    )
    if not proximo or dt.datetime.fromisoformat(proximo["inicio"]) - ahora > HORIZONTE:
        return "LISTA PARTIDO · sin partido esta semana", "No hay partido en los próximos días. 🏖️"

    nombres = {j["id"]: j["nombre"] for j in data["jugadores"]}
    grupos = {"si": [], "duda": [], "no": []}
    respondidos = set()
    for fila in leer_asistencia(proximo["id"]):
        grupos[fila["estado"]].append(nombres.get(fila["jugador_id"], f"Jugador {fila['jugador_id']}"))
        respondidos.add(fila["jugador_id"])
    sin_resp = [n for i, n in nombres.items() if i not in respondidos]

    def linea(icono, titulo, lista):
        return f"{icono} *{titulo} ({len(lista)})*: " + (", ".join(sorted(lista)) if lista else "—")

    ini = dt.datetime.fromisoformat(proximo["inicio"])
    out = [
        f"⚽ *{data.get('equipo', 'FCN Bar Orreaga')}* vs *{proximo['rival']}* ({'local' if proximo['local'] else 'visitante'})",
        f"📅 {fecha_larga(ini)}",
        f"📍 {proximo['lugar']}",
    ]
    if proximo.get("arbitros"):
        out.append(f"🧑‍⚖️ {', '.join(proximo['arbitros'])}")
    out += [
        "",
        linea("✅", "Van", grupos["si"]),
        linea("❓", "Duda", grupos["duda"]),
        linea("❌", "No", grupos["no"]),
        linea("⏳", "Sin responder", sin_resp),
    ]
    minimo = minimo_jugadores()
    if len(grupos["si"]) < minimo:
        out += ["", f"⚠️ Faltan {minimo - len(grupos['si'])} para llegar a {minimo}"]
    if web_url():
        out += ["", f"Apuntaos aquí 👉 {web_url()}"]
    return f"LISTA PARTIDO vs {proximo['rival']}", "\n".join(out)


def enviar(asunto, texto):
    """Envía el correo con una contraseña de aplicación de Gmail."""
    usuario = os.environ.get("GMAIL_USER", "")
    clave = os.environ.get("GMAIL_APP_PASSWORD", "")
    destino = os.environ.get("MAIL_TO", "") or usuario
    if not usuario or not clave:
        sys.exit("Faltan GMAIL_USER y GMAIL_APP_PASSWORD")
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = usuario
    msg["To"] = destino
    msg.set_content(texto)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(usuario, clave)
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="fecha y hora de Pamplona a simular, p. ej. 2026-10-24T08:00")
    ap.add_argument("--enviar", action="store_true", help="enviar por correo además de imprimir")
    args = ap.parse_args()
    ahora = (dt.datetime.fromisoformat(args.now) if args.now
             else dt.datetime.now(ZoneInfo("Europe/Madrid")).replace(tzinfo=None))
    data = json.loads((DOCS / "partidos.json").read_text(encoding="utf-8"))
    asunto, texto = mensaje(data, ahora)
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{asunto}\n\n{texto}")
    if args.enviar:
        enviar(asunto, texto)


if __name__ == "__main__":
    main()
