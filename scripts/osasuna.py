#!/usr/bin/env python3
"""Calendario personal: partidos de Osasuna en El Sadar (LaLiga y Copa del Rey).

Genera docs/osasuna.ics a partir de la API pública de ESPN. Es independiente de la web
de FCN Bar Orreaga: no toca partidos.json ni calendario.ics.

- Partido con día y hora confirmados -> evento con su hora real.
- Jornada sin horario fijado por LaLiga -> evento de día completo que cubre todo el
  fin de semana (viernes a lunes), o martes a jueves si es jornada entre semana.
  Cuando LaLiga fija la hora, el mismo evento (mismo UID) pasa a tener la hora real.

Solo usa la librería estándar. Uso:
    python scripts/osasuna.py
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TEAM_ID = "97"  # Osasuna en ESPN
COMPETICIONES = {"esp.1": "LaLiga", "esp.copa_del_rey": "Copa del Rey"}
DURACION = dt.timedelta(hours=2)
NOMBRES = {  # nombres de ESPN (en inglés) -> como se dicen aquí
    "Celta Vigo": "Celta",
    "Atlético Madrid": "Atlético de Madrid",
    "Athletic Club": "Athletic",
    "Real Betis": "Betis",
    "Racing Santander": "Racing",
    "Rayo Vallecano": "Rayo",
}

ROOT = Path(__file__).resolve().parent.parent
ICS_OUT = ROOT / "docs" / "osasuna.ics"


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "OsasunaCalendario/1.0"})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            if intento == 2:
                raise
            print(f"  reintento {url}: {e}")
            time.sleep(3)


def partidos_en_casa():
    """Partidos de Osasuna como local en El Sadar, jugados y por jugar, sin duplicados."""
    eventos = {}
    for liga, nombre_comp in COMPETICIONES.items():
        # Sin parámetro: resultados ya jugados. Con fixture=true: los que quedan.
        for sufijo in ("", "?fixture=true"):
            datos = get(f"{API}/{liga}/teams/{TEAM_ID}/schedule{sufijo}")
            for e in datos.get("events", []):
                e["_competicion"] = nombre_comp
                e["_ronda"] = e.get("seasonType", {}).get("name", "")
                eventos[e["id"]] = e

    partidos = []
    for e in eventos.values():
        c = e["competitions"][0]
        local = next(t for t in c["competitors"] if t["homeAway"] == "home")
        rival = next(t for t in c["competitors"] if t["homeAway"] == "away")
        estadio = (c.get("venue") or {}).get("fullName", "")
        estado = c["status"]["type"]["name"]
        # En casa = Osasuna local y en El Sadar (descarta una final de Copa en campo neutral).
        if local["team"]["id"] != TEAM_ID or (estadio and "Sadar" not in estadio):
            continue
        if estado == "STATUS_CANCELED":
            continue
        nombre_rival = rival["team"]["displayName"]
        partidos.append({
            "id": e["id"],
            "competicion": e["_competicion"],
            "ronda": e["_ronda"] if e["_competicion"] != "LaLiga" else "",
            "rival": NOMBRES.get(nombre_rival, nombre_rival),
            "inicio": dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")),
            "hora_fijada": bool(c.get("timeValid")) and estado != "STATUS_POSTPONED",
            "jugado": estado in ("STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET", "STATUS_FINAL_PEN"),
            "goles": (local.get("score") or {}).get("displayValue"),
            "goles_rival": (rival.get("score") or {}).get("displayValue"),
        })
    partidos.sort(key=lambda p: p["inicio"])
    return partidos


def ventana_sin_horario(fecha):
    """Días que puede ocupar una jornada aún sin horario: [inicio, fin) para DTEND exclusivo."""
    if fecha.weekday() in (1, 2, 3):  # martes-jueves: jornada entre semana
        ini = fecha - dt.timedelta(days=fecha.weekday() - 1)
        return ini, ini + dt.timedelta(days=3)
    # viernes a lunes del fin de semana que contiene la fecha
    ini = fecha - dt.timedelta(days=(fecha.weekday() - 4) % 7)
    return ini, ini + dt.timedelta(days=4)


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


def generar_ics(partidos, stamp):
    L = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Iker//Osasuna en El Sadar//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Osasuna en El Sadar", "X-WR-TIMEZONE:Europe/Madrid",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
    ]
    for p in partidos:
        titulo = f"Osasuna vs {p['rival']}"
        if p["jugado"] and p["goles"] is not None:
            titulo += f" ({p['goles']}-{p['goles_rival']})"
        if p["competicion"] != "LaLiga":
            titulo += f" · {p['competicion']}"
        desc = [p["competicion"] + (f" · {p['ronda']}" if p["ronda"] else "")]
        if p["hora_fijada"]:
            fechas = [
                f"DTSTART:{p['inicio']:%Y%m%dT%H%M%SZ}",
                f"DTEND:{p['inicio'] + DURACION:%Y%m%dT%H%M%SZ}",
            ]
        else:
            ini, fin = ventana_sin_horario(p["inicio"].date())
            titulo += " (sin horario)"
            desc.append("LaLiga aún no ha fijado día y hora. Se actualizará solo cuando se publique.")
            fechas = [f"DTSTART;VALUE=DATE:{ini:%Y%m%d}", f"DTEND;VALUE=DATE:{fin:%Y%m%d}"]
        L += [
            "BEGIN:VEVENT",
            f"UID:espn-{p['id']}@osasuna-sadar",
            f"DTSTAMP:{stamp}",
            *fechas,
            f"SUMMARY:{esc(('🔴 ' if p['hora_fijada'] else '⏳ ') + titulo)}",
            f"LOCATION:{esc('Estadio El Sadar, Pamplona')}",
            f"DESCRIPTION:{esc(chr(10).join(desc))}",
            "TRANSP:TRANSPARENT" if not p["hora_fijada"] else "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    L.append("END:VCALENDAR")
    return "\r\n".join(plegar(x) for x in L) + "\r\n"


def main():
    partidos = partidos_en_casa()
    # Solo cambia DTSTAMP si cambia algo: así no hay commits vacíos.
    previo = ICS_OUT.read_text(encoding="utf-8") if ICS_OUT.exists() else ""
    stamp_previo = next((l[8:] for l in previo.splitlines() if l.startswith("DTSTAMP:")), None)
    stamp = stamp_previo or "19700101T000000Z"
    ics = generar_ics(partidos, stamp)
    if ics != previo:
        ics = generar_ics(partidos, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        with open(ICS_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(ics)
    pendientes = [p for p in partidos if not p["jugado"]]
    sin_hora = [p for p in pendientes if not p["hora_fijada"]]
    print(f"{len(partidos)} partidos en El Sadar ({len(pendientes)} por jugar, {len(sin_hora)} sin horario)")


if __name__ == "__main__":
    main()
