# FCN Bar Orreaga · Calendario y asistencia

Web del equipo en FS5 Navarra. Muestra el calendario con rival, hora, lugar y árbitro, deja que cada jugador marque si va al partido y ofrece un calendario suscribible para Google Calendar o iPhone. Todo funciona en planes gratuitos.

```
GitHub Action (2 veces al día)
  └─ scripts/fetch.py ── API pública de fs5navarra.es
       ├─ docs/partidos.json   → la web
       └─ docs/calendario.ics  → Google Calendar (suscripción)
GitHub Pages ── docs/index.html
Supabase (gratis) ── asistencia, protegida con PIN
```

## Puesta en marcha (unos 15 minutos)

### 1. Repositorio
1. Crea un repo en GitHub (por ejemplo `orreaga`) y sube este contenido.
2. Ve a **Settings → Pages → Source** y elige **GitHub Actions**.
3. Ve a **Settings → Actions → General → Workflow permissions** y elige **Read and write**.

### 2. Supabase (asistencia)
1. Crea un proyecto gratuito en supabase.com. Para la región, elige Europa.
2. Abre `supabase/schema.sql`, cambia `CAMBIA-ESTE-PIN` por vuestro PIN, pégalo en **SQL Editor** y pulsa **Run**.
3. En **Project Settings → API** copia la *Project URL* y la clave **publishable / anon**. La `service_role` / `secret` no la uses nunca.
4. Pega ambas en `docs/config.js`.
5. En GitHub, ve a **Settings → Secrets and variables → Actions** y añade `SUPABASE_URL` y `SUPABASE_KEY` con esos mismos valores. Sirven para que la Action haga una lectura diaria y el proyecto no se pause por inactividad.

### 3. Primer despliegue
En la pestaña **Actions**, abre **Actualizar calendario** y pulsa **Run workflow**. La web quedará en `https://<tu-usuario>.github.io/<repo>/`.

### 4. Para el equipo
- Pasad por el grupo el enlace y el PIN.
- Cada uno elige su nombre la primera vez; el móvil lo recuerda.
- Para el calendario, pulsad **Google Calendar** en la web, una vez. En iPhone, **iPhone / Apple**.

## Detalles
- **Árbitros:** FS5 los asigna poco antes del partido. El script consulta la ficha de los partidos de los próximos 21 días, así que aparecen solos cuando se publican.
- **Cambios de horario:** se reflejan en la web en la siguiente ejecución (07:17 o 17:17). Google Calendar refresca las suscripciones cada pocas horas, no al instante.
- **Plantilla:** sale de la ficha del equipo en FS5. Si alguien se da de alta allí, aparece solo.
- **Otra temporada o competición:** cambia `TOURNAMENT_ID` (y `TEAM_ID` si cambia) en `scripts/fetch.py`. Los dos aparecen en la URL de la ficha del equipo en fs5navarra.es.
- **Temas:** los botones 1ª y 2ª cambian entre la equipación de rayas negras y moradas (oscuro) y la blanca con morado y rosa (claro).

## Limitaciones conocidas
- **Seguridad:** el PIN es compartido y cualquiera que lo tenga puede marcar por otro jugador. Para un equipo de amigos es suficiente. Si se filtra, cámbialo con `update public.ajustes set valor = 'nuevo' where clave = 'pin';`.
- **Visibilidad:** la web es pública. Muestra nombres abreviados (Iker U.) y la asistencia. Los datos de partidos ya son públicos en FS5.
- **Dependencia de FS5:** la API no es oficial para terceros. Si FS5 cambia su web, el script puede dejar de funcionar. En ese caso la web sigue mostrando los últimos datos guardados.
