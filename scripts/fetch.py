#!/usr/bin/env python3
"""Descarga el calendario de FCN Bar Orreaga desde la web de FS5 Navarra
y genera docs/partidos.json (para la web) y docs/calendario.ics (para Google Calendar).

Solo usa la librería estándar. Uso:
    python scripts/fetch.py                       # datos reales
    python scripts/fetch.py --fixtures tests/fixtures --now 2026-10-20   # pruebas sin red
"""
import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.fs5navarra.es/api"
WEB = "https://www.fs5navarra.es"
TEAM_ID = int(os.environ.get("FS5_TEAM_ID", 2556))
TOURNAMENT_ID = int(os.environ.get("FS5_TOURNAMENT_ID", 143))
EQUIPO = "FCN Bar Orreaga"
COMPETICION = "FS5 Navarra · Fin de semana · 3ª División Grupo III"
# Solo se consulta la ficha (árbitro, dirección) de los partidos en esta ventana:
# los árbitros se asignan poco antes y así se hacen muy pocas peticiones.
VENTANA_PASADO = dt.timedelta(days=3)
VENTANA_FUTURO = dt.timedelta(days=21)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
JSON_OUT = DOCS / "partidos.json"
ICS_OUT = DOCS / "calendario.ics"


def get(path, fixtures=None):
    """GET a la API de FS5 (o lee el fixture equivalente en modo prueba)."""
    if fixtures:
        f = Path(fixtures) / (path.replace("/", "_") + ".json")
        if not f.exists():
            raise FileNotFoundError(f)
        return json.loads(f.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        f"{BASE}/{path}",
        headers={"Accept": "application/json", "User-Agent": "OrreagaCalendario/1.0 (calendario del equipo)"},
    )
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            if intento == 2:
                raise
            print(f"  reintento {path}: {e}")
            time.sleep(3)


def nombre_corto(nombre, apellidos):
    """'IÑIGO', 'EGÜES MENDIOROZ' -> 'Iñigo E.'"""
    n = (nombre or "").strip().split()
    a = (apellidos or "").strip().split()
    base = n[0].capitalize() if n else "Jugador"
    return f"{base} {a[0][0].upper()}." if a else base


def cargar_previo():
    if JSON_OUT.exists():
        try:
            return json.loads(JSON_OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def construir(fixtures=None, ahora=None):
    ahora = ahora or dt.datetime.now()
    previo = cargar_previo()
    prev_partidos = {p["id"]: p for p in previo.get("partidos", [])}
    campos = {int(k): v for k, v in previo.get("campos", {}).items()}

    equipo = get(f"teams/{TEAM_ID}/details/{TOURNAMENT_ID}", fixtures)

    jugadores = sorted(
        (
            {"id": p["userData"]["id"], "nombre": nombre_corto(p.get("name"), p.get("surname"))}
            for p in equipo.get("players", [])
            if p.get("userData", {}).get("id")
        ),
        key=lambda j: j["nombre"],
    )

    partidos = []
    for jornada in equipo.get("days", []):
        for m in jornada.get("matches") or []:
            local = m["idHomeTeam"] == TEAM_ID
            rival = (m["visitorTeam"] if local else m["homeTeam"])["name"]
            inicio = dt.datetime.fromisoformat(m["startTime"])
            jugado = m.get("status", 0) >= 5
            prev = prev_partidos.get(m["id"], {})
            campo = m.get("field") or {}
            p = {
                "id": m["id"],
                "jornada": jornada.get("name", ""),
                "inicio": m["startTime"][:16],  # hora local de Pamplona, sin zona
                "duracion": m.get("duration", 50),
                "local": local,
                "rival": rival,
                "campo_id": campo.get("id"),
                "lugar": campo.get("name", ""),
                "estado": "jugado" if jugado else "programado",
                "goles_favor": (m["homeScore"] if local else m["visitorScore"]) if jugado else None,
                "goles_contra": (m["visitorScore"] if local else m["homeScore"]) if jugado else None,
                "arbitros": prev.get("arbitros", []),
                "url": f"{WEB}/tournaments/{TOURNAMENT_ID}/matches/{m['id']}",
            }
            if ahora - VENTANA_PASADO <= inicio <= ahora + VENTANA_FUTURO:
                try:
                    det = get(f"matches/{m['id']}", fixtures)
                    p["arbitros"] = [
                        r["referee"]["name"].strip()
                        for r in det.get("referees") or []
                        if r.get("referee", {}).get("name")
                    ]
                    f = det.get("field") or {}
                    if f.get("id"):
                        campos[f["id"]] = {
                            "nombre": f.get("name", ""),
                            "direccion": ", ".join(x for x in [f.get("address"), f.get("location")] if x),
                        }
                    if not fixtures:
                        time.sleep(1)
                except Exception as e:  # una ficha caída no debe tumbar el resto
                    print(f"  sin ficha del partido {m['id']}: {e}")
            partidos.append(p)

    partidos.sort(key=lambda p: p["inicio"])
    for p in partidos:
        p["direccion"] = campos.get(p["campo_id"], {}).get("direccion", "")

    datos = {
        "equipo": EQUIPO,
        "competicion": COMPETICION,
        "fuente": f"{WEB}/tournaments/{TOURNAMENT_ID}",
        "jugadores": jugadores,
        "campos": {str(k): v for k, v in sorted(campos.items())},
        "partidos": partidos,
    }
    # Solo cambia la marca de tiempo si cambian los datos: así no hay commits vacíos.
    sin_marca = {k: v for k, v in previo.items() if k != "actualizado"}
    datos["actualizado"] = (
        previo["actualizado"]
        if sin_marca == datos and "actualizado" in previo
        else dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    return datos


# ---------- iCalendar ----------

def esc(texto):
    return texto.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def plegar(linea):
    """Pliega líneas a 75 octetos (RFC 5545) sin partir caracteres UTF-8."""
    out, actual = [], ""
    for ch in linea:
        limite = 75 if not out else 74
        if len((actual + ch).encode("utf-8")) > limite:
            out.append(actual)
            actual = ch
        else:
            actual += ch
    out.append(actual)
    return "\r\n ".join(out)


def generar_ics(datos):
    stamp = datos["actualizado"].replace("-", "").replace(":", "")
    L = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//FCN Bar Orreaga//Calendario FS5//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(datos['equipo'])}", "X-WR-TIMEZONE:Europe/Madrid",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
        "BEGIN:VTIMEZONE", "TZID:Europe/Madrid",
        "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
        "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
        "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
        "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for p in datos["partidos"]:
        ini = dt.datetime.fromisoformat(p["inicio"])
        fin = ini + dt.timedelta(minutes=p["duracion"])
        titulo = f"{datos['equipo']} vs {p['rival']}" if p["local"] else f"{p['rival']} vs {datos['equipo']}"
        if p["estado"] == "jugado":
            titulo += f" ({p['goles_favor']}-{p['goles_contra']})"
        desc = [
            f"{p['jornada']} · {'Local' if p['local'] else 'Visitante'}",
            f"Árbitro: {', '.join(p['arbitros']) if p['arbitros'] else 'pendiente de asignar'}",
            p["url"],
        ]
        lugar = p["lugar"] + (f", {p['direccion']}" if p["direccion"] else ", Navarra")
        L += [
            "BEGIN:VEVENT",
            f"UID:fs5-match-{p['id']}@fcn-bar-orreaga",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=Europe/Madrid:{ini:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Europe/Madrid:{fin:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc('⚽ ' + titulo)}",
            f"LOCATION:{esc(lugar)}",
            f"DESCRIPTION:{esc(chr(10).join(desc))}",
            f"URL:{p['url']}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Partido", "TRIGGER:-PT2H", "END:VALARM",
            "END:VEVENT",
        ]
    L.append("END:VCALENDAR")
    return "\r\n".join(plegar(x) for x in L) + "\r\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", help="carpeta con respuestas JSON guardadas (modo prueba)")
    ap.add_argument("--now", help="fecha actual simulada, AAAA-MM-DD (modo prueba)")
    a = ap.parse_args()
    ahora = dt.datetime.fromisoformat(a.now) if a.now else None
    datos = construir(a.fixtures, ahora)
    DOCS.mkdir(exist_ok=True)
    JSON_OUT.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(ICS_OUT, "w", encoding="utf-8", newline="") as f:
        f.write(generar_ics(datos))
    proximos = [p for p in datos["partidos"] if p["estado"] == "programado"]
    print(f"{len(datos['partidos'])} partidos ({len(proximos)} por jugar), {len(datos['jugadores'])} jugadores")


if __name__ == "__main__":
    main()
