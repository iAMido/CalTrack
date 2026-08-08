-- Stage 4 — caltrack_runs reads RunCoach directly
--
-- Applied to production 2026-08-08. Recorded here for reproducibility.
--
-- WHY
-- CalTrack's Strava sync stopped on 2026-06-29 (Strava deactivated the API
-- application). From 2026-06-30 to 2026-08-06 the dashboard counted ZERO
-- exercise calories across 18 runs / 118.1 km / 9,450 kcal, so net intake in
-- app/api/caltrack/overview/route.ts was overstated for five weeks. RunCoach
-- kept syncing into the same Supabase project, so the data was already here.
--
-- CALORIE CHANGEOVER DATE: 2026-06-29
-- RunCoach's calories differ from CalTrack's on ALL 28 historical runs
-- (0 identical; mean absolute delta 30.4 kcal; range -137..+108; net only
-- -81 kcal, which is why the differences cancel and stay invisible in totals).
-- Cause: bot/services/strava.py:159 stored `strava_calories or MET_fallback`,
-- while RunCoach stored its own value for the same activity. They were never
-- the same series.
--
-- Serving history from RunCoach would therefore retroactively restate a
-- deficit/weight history that has already been reconciled. So the view is a
-- UNION with an explicit cutover:
--   <= 2026-06-29  ->  preserved physical rows (public._bak_caltrack_runs)
--   >= 2026-06-30  ->  live runcoach.runs
--
-- WRITES
-- caltrack_runs is NOT read-only. Two live write paths exist in the bot:
--   bot/handlers/commands.py:134  (/run manual logging)
--   bot/services/strava.py:219    (Strava sync, currently inactive)
-- A view is not writable without triggers, so INSTEAD OF triggers route all
-- writes to the retained physical table. No CalTrack code changed.
--
-- PERMISSIONS
-- security_invoker = on is deliberate. The default (security definer) would
-- run the view as its owner and let anon/authenticated bypass RLS on
-- runcoach.runs. With invoker, service_role (which bypasses RLS) still reads
-- everything and every other role keeps its existing semantics.
--
-- REVERSIBLE
--   drop view public.caltrack_runs cascade;
--   alter table public._bak_caltrack_runs rename to caltrack_runs;

alter table public.caltrack_runs rename to _bak_caltrack_runs;

create view public.caltrack_runs
with (security_invoker = on) as
  select
    id, user_id, distance_km, duration_minutes, avg_pace_sec_per_km,
    avg_heart_rate, max_heart_rate, calories_burned, elevation_gain_m,
    source, external_id, external_url, run_date, created_at
  from public._bak_caltrack_runs
union all
  select
    r.id,
    -- runcoach.runs.user_id is TEXT (an email); caltrack_runs.user_id is UUID.
    -- Unrelated identifiers, not two encodings of one value: map explicitly.
    case r.user_id
      when 'idomosseri@gmail.com' then '95d01655-1383-452e-a463-d3cb2bf2885d'::uuid
    end                                    as user_id,
    r.distance_km,
    round(r.duration_min)::int             as duration_minutes,
    round(r.avg_pace_min_km * 60)::int     as avg_pace_sec_per_km,
    r.avg_hr                               as avg_heart_rate,
    r.max_hr                               as max_heart_rate,
    r.calories::int                        as calories_burned,
    null::int                              as elevation_gain_m,  -- not stored in runcoach
    r.data_source                          as source,
    r.filename                             as external_id,
    null::text                             as external_url,      -- was the Strava link
    r.date                                 as run_date,
    r.created_at
  from runcoach.runs r
  where r.date >= timestamptz '2026-06-30 00:00:00+03'
    and r.user_id = 'idomosseri@gmail.com';

comment on view public.caltrack_runs is
  'Union of preserved CalTrack rows (<= 2026-06-29) and live runcoach.runs '
  '(>= 2026-06-30). Writes are routed to public._bak_caltrack_runs by INSTEAD '
  'OF triggers. Calorie changeover date: 2026-06-29.';

grant select, insert, update, delete, references, trigger
  on public.caltrack_runs to postgres, anon, authenticated, service_role;

-- A view has no column defaults, so unsupplied columns arrive as NULL and the
-- table defaults (gen_random_uuid(), now()) must be re-applied here.
create or replace function public.caltrack_runs_insert()
returns trigger language plpgsql set search_path = public as $$
begin
  insert into public._bak_caltrack_runs (
    id, user_id, distance_km, duration_minutes, avg_pace_sec_per_km,
    avg_heart_rate, max_heart_rate, calories_burned, elevation_gain_m,
    source, external_id, external_url, run_date, created_at
  ) values (
    coalesce(new.id, gen_random_uuid()),
    new.user_id, new.distance_km, new.duration_minutes, new.avg_pace_sec_per_km,
    new.avg_heart_rate, new.max_heart_rate, new.calories_burned,
    new.elevation_gain_m, new.source, new.external_id, new.external_url,
    coalesce(new.run_date, now()), coalesce(new.created_at, now())
  )
  returning * into new;
  return new;
end $$;

create or replace function public.caltrack_runs_update()
returns trigger language plpgsql set search_path = public as $$
begin
  update public._bak_caltrack_runs set
    user_id = new.user_id, distance_km = new.distance_km,
    duration_minutes = new.duration_minutes,
    avg_pace_sec_per_km = new.avg_pace_sec_per_km,
    avg_heart_rate = new.avg_heart_rate, max_heart_rate = new.max_heart_rate,
    calories_burned = new.calories_burned,
    elevation_gain_m = new.elevation_gain_m, source = new.source,
    external_id = new.external_id, external_url = new.external_url,
    run_date = new.run_date
  where id = old.id;

  if not found then
    raise exception
      'caltrack_runs row % is RunCoach-sourced and read-only from CalTrack; '
      'edit it in RunCoach instead', old.id
      using errcode = 'read_only_sql_transaction';
  end if;
  return new;
end $$;

create or replace function public.caltrack_runs_delete()
returns trigger language plpgsql set search_path = public as $$
begin
  delete from public._bak_caltrack_runs where id = old.id;

  if not found then
    raise exception
      'caltrack_runs row % is RunCoach-sourced and read-only from CalTrack; '
      'delete it in RunCoach instead', old.id
      using errcode = 'read_only_sql_transaction';
  end if;
  return old;
end $$;

create trigger caltrack_runs_insert_trg
  instead of insert on public.caltrack_runs
  for each row execute function public.caltrack_runs_insert();

create trigger caltrack_runs_update_trg
  instead of update on public.caltrack_runs
  for each row execute function public.caltrack_runs_update();

create trigger caltrack_runs_delete_trg
  instead of delete on public.caltrack_runs
  for each row execute function public.caltrack_runs_delete();
