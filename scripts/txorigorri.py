#!/usr/bin/env python3
"""Calendario personal: partidos de Txorigorri F.T. en la Liga Fin de Semana de F7 Navarra.

Genera docs/txorigorri.ics a partir de la API pública de Playooz (la plataforma de
f7navarra.com). Es independiente de la web de FCN Bar Orreaga.

- Partido con hora -> evento con su hora real.
- Partido con fecha pero sin hora -> evento de día completo de viernes a lunes.
- Partido sin fecha -> no aparece hasta que la tenga.

Solo usa la librería estándar. Uso:
    python scripts/txorigorri.py
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from osasuna import esc, plegar, ventana_sin_horario

API = "https://api.playooz.com"
TENANT = "f7navarra.com"
EVENT_ID = 356  # Liga Fin de Semana 2026/2027
EVENT_RUTA = "liga-fin-de-semana-20262027"
TEAM_ID = 2723
EQUIPO = "Txorigorri"
DURACION = dt.timedelta(minutes=60)

ROOT = Path(__file__).resolve().parent.parent
ICS_OUT = ROOT / "docs" / "txorigorri.ics"


def get(path):
    req = urllib.request.Request(
        f"{API}/{path}",
        headers={"Accept": "application/json", "X-Tenant-Host": TENANT, "X-Language": "es",
                 "User-Agent": "TxorigorriCalendario/1.0"},
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


def nombre(n):
    return EQUIPO if n.startswith("Txorigorri") else n


def partidos():
    cal = get(f"team/event/{EVENT_ID}/{TEAM_ID}")["calendar"]
    out = []
    for m in cal.get("played", []) + cal.get("pending", []):
        if m.get("isBye") or not m.get("date"):
            continue
        inicio = dt.datetime.fromisoformat(m["date"][:19])
        out.append({
            "id": m["matchId"],
            "jornada": m.get("fixtureName", ""),
            "fase": " · ".join(x for x in [m.get("roundName"), m.get("groupName")] if x),
            "inicio": inicio,
            "hora_fijada": bool(m.get("start")) and m["start"] != "00:00:00",
            "jugado": m.get("status", 0) >= 5,
            "titulo": f"{nombre(m['homeName'])} vs {nombre(m['awayName'])}",
            "marcador": f"{m['scoreHome']}-{m['scoreAway']}" if m.get("scoreHome") is not None else None,
            "local": m["homeId"] == TEAM_ID,
            "lugar": " · ".join(x for x in [m.get("facilityAlias"), m.get("fieldName")] if x),
        })
    out.sort(key=lambda p: p["inicio"])
    return out


def generar_ics(lista, stamp):
    L = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Iker//Txorigorri F7//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{EQUIPO} F7", "X-WR-TIMEZONE:Europe/Madrid",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
        "BEGIN:VTIMEZONE", "TZID:Europe/Madrid",
        "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
        "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
        "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
        "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for p in lista:
        titulo = p["titulo"] + (f" ({p['marcador']})" if p["jugado"] and p["marcador"] else "")
        desc = [f"{p['jornada']} · {'Local' if p['local'] else 'Visitante'}", p["fase"],
                f"https://{TENANT}/{EVENT_RUTA}/equipo/{TEAM_ID}/txorigorri-ft"]
        if p["hora_fijada"]:
            fechas = [
                f"DTSTART;TZID=Europe/Madrid:{p['inicio']:%Y%m%dT%H%M%S}",
                f"DTEND;TZID=Europe/Madrid:{p['inicio'] + DURACION:%Y%m%dT%H%M%S}",
            ]
        else:
            ini, fin = ventana_sin_horario(p["inicio"].date())
            titulo += " (sin horario)"
            fechas = [f"DTSTART;VALUE=DATE:{ini:%Y%m%d}", f"DTEND;VALUE=DATE:{fin:%Y%m%d}"]
        L += [
            "BEGIN:VEVENT",
            f"UID:f7-match-{p['id']}@txorigorri",
            f"DTSTAMP:{stamp}",
            *fechas,
            f"SUMMARY:{esc(('⚽ ' if p['hora_fijada'] else '⏳ ') + titulo)}",
            f"LOCATION:{esc(p['lugar'] + ', Pamplona')}",
            f"DESCRIPTION:{esc(chr(10).join(x for x in desc if x))}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Partido", "TRIGGER:-PT2H", "END:VALARM",
            "END:VEVENT",
        ]
    L.append("END:VCALENDAR")
    return "\r\n".join(plegar(x) for x in L) + "\r\n"


def main():
    lista = partidos()
    # Solo cambia DTSTAMP si cambia algo: así no hay commits vacíos.
    previo = ICS_OUT.read_text(encoding="utf-8") if ICS_OUT.exists() else ""
    stamp_previo = next((l[8:] for l in previo.splitlines() if l.startswith("DTSTAMP:")), None)
    ics = generar_ics(lista, stamp_previo or "19700101T000000Z")
    if ics != previo:
        ics = generar_ics(lista, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        with open(ICS_OUT, "w", encoding="utf-8", newline="") as f:
            f.write(ics)
    pendientes = [p for p in lista if not p["jugado"]]
    print(f"{len(lista)} partidos de {EQUIPO} ({len(pendientes)} por jugar)")


if __name__ == "__main__":
    main()
