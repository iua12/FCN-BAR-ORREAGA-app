-- Asistencia FCN Bar Orreaga
-- Pégalo entero en Supabase → SQL Editor → Run.
-- Antes, cambia 'CAMBIA-ESTE-PIN' por el PIN del equipo (mejor una palabra que 4 cifras).

create table if not exists public.asistencia (
  partido_id  bigint      not null,
  jugador_id  bigint      not null,
  estado      text        not null check (estado in ('si', 'duda', 'no')),
  actualizado timestamptz not null default now(),
  primary key (partido_id, jugador_id)
);

alter table public.asistencia enable row level security;

-- Cualquiera con la web puede VER quién va; nadie puede escribir directamente.
drop policy if exists "lectura publica" on public.asistencia;
create policy "lectura publica" on public.asistencia
  for select to anon, authenticated using (true);
-- Los proyectos nuevos no dan permisos de tabla a anon por defecto: sin esto la política no basta.
grant select on public.asistencia to anon, authenticated;

-- Ajustes privados (el PIN). Sin políticas: la clave pública no puede leerla.
create table if not exists public.ajustes (
  clave text primary key,
  valor text not null
);
alter table public.ajustes enable row level security;

insert into public.ajustes (clave, valor) values ('pin', 'CAMBIA-ESTE-PIN')
on conflict (clave) do update set valor = excluded.valor;

-- Única vía de escritura: comprueba el PIN y guarda (o borra, si p_estado es null).
create or replace function public.votar(p_partido bigint, p_jugador bigint, p_estado text, p_pin text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_pin is distinct from (select valor from ajustes where clave = 'pin') then
    raise exception 'PIN incorrecto' using errcode = '28000';
  end if;
  if p_estado is null then
    delete from asistencia where partido_id = p_partido and jugador_id = p_jugador;
  else
    insert into asistencia (partido_id, jugador_id, estado)
    values (p_partido, p_jugador, p_estado)
    on conflict (partido_id, jugador_id)
    do update set estado = excluded.estado, actualizado = now();
  end if;
end;
$$;

create or replace function public.comprobar_pin(p_pin text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select coalesce(p_pin = (select valor from ajustes where clave = 'pin'), false);
$$;

revoke all on function public.votar(bigint, bigint, text, text) from public;
revoke all on function public.comprobar_pin(text) from public;
grant execute on function public.votar(bigint, bigint, text, text) to anon, authenticated;
grant execute on function public.comprobar_pin(text) to anon, authenticated;

-- Para cambiar el PIN más adelante:
-- update public.ajustes set valor = 'nuevo-pin' where clave = 'pin';
