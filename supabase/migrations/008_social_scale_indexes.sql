-- Scaling indexes and index-friendly search for public.mml_social_page.
-- Apply after 001–007 (depends on 001–005). Transactional and safe to replay.
-- Preserves all privacy boundaries, RLS policies, moderation rules and RPC permissions.
begin;

-- Support ordered keyset pagination of public usernames under C collation
-- regardless of the database's default locale.
create index if not exists mml_usernames_username_c
    on mml_private.usernames (username collate "C", user_id);

-- Partial expression indexes on active watched films with an explicit watched_date
-- to accelerate the "This week" feed (both global and search-filtered queries).
create index if not exists mml_library_active_watched_date
    on public.mml_library ((data->>'watched_date') desc, user_id, record_key)
    where data->'deleted_at' = 'null'::jsonb
      and data->>'status' = 'Watched'
      and data->>'watched_date' is not null;

create index if not exists mml_library_user_active_watched_date
    on public.mml_library (user_id, (data->>'watched_date') desc, record_key)
    where data->'deleted_at' = 'null'::jsonb
      and data->>'status' = 'Watched'
      and data->>'watched_date' is not null;

-- Enable pg_trgm when available (PostgreSQL / Supabase / PGlite with contrib/pg_trgm)
-- and build GIN trigram indexes for substring search on lower(username) and
-- public lower(display_name). Fall back to text_pattern_ops B-tree indexes when
-- pg_trgm is unavailable in a minimal test runtime.
do $$
declare
    trgm_schema text;
begin
    select n.nspname into trgm_schema
    from pg_catalog.pg_extension e
    join pg_catalog.pg_namespace n on n.oid = e.extnamespace
    where e.extname = 'pg_trgm';

    if trgm_schema is null and exists (
        select 1 from pg_catalog.pg_available_extensions where name = 'pg_trgm'
    ) then
        begin
            if exists (select 1 from pg_catalog.pg_namespace where nspname = 'extensions') then
                execute 'create extension if not exists pg_trgm with schema extensions';
            else
                execute 'create extension if not exists pg_trgm';
            end if;
        exception when insufficient_privilege or feature_not_supported or undefined_file then
            null;
        end;

        select n.nspname into trgm_schema
        from pg_catalog.pg_extension e
        join pg_catalog.pg_namespace n on n.oid = e.extnamespace
        where e.extname = 'pg_trgm';
    end if;

    if trgm_schema is not null then
        execute format(
            'create index if not exists mml_usernames_username_trgm on mml_private.usernames using gin (lower(username) %I.gin_trgm_ops)',
            trgm_schema
        );
        execute format(
            'create index if not exists mml_profiles_display_name_trgm on mml_private.profiles using gin (lower(display_name) %I.gin_trgm_ops) where is_public',
            trgm_schema
        );
        execute 'drop index if exists mml_private.mml_usernames_username_pattern';
        execute 'drop index if exists mml_private.mml_profiles_display_name_pattern';
    else
        execute 'create index if not exists mml_usernames_username_pattern on mml_private.usernames (lower(username) text_pattern_ops)';
        execute 'create index if not exists mml_profiles_display_name_pattern on mml_private.profiles (lower(display_name) text_pattern_ops) where is_public';
    end if;
end;
$$;

create or replace function public.mml_social_page(
    p_view text default 'people', p_query text default '', p_cursor jsonb default null
) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare
    today date := (now() at time zone 'UTC')::date;
    first_day date := today - (extract(isodow from today)::int - 1);
    search text := lower(btrim(p_query));
    search_pattern text;
    cur_name text;
    cur_date text;
    cur_film bigint;
    upper_date text;
    entries jsonb;
    last_entry jsonb;
    next_page jsonb := null;
    cap int;
begin
    if p_view is null or p_view not in ('people','week') or p_query is null
       or char_length(p_query)>60 or p_query ~ '[[:cntrl:]]' then
        raise exception using errcode='22023', message='Invalid social search.';
    end if;
    if search <> '' then
        search_pattern := '%' || replace(replace(replace(search, E'\\', E'\\\\'), '%', E'\\%'), '_', E'\\_') || '%';
    end if;
    cap := case when p_view='people' then 16 else 12 end;
    if p_cursor is not null then
        if jsonb_typeof(p_cursor)<>'object' or jsonb_typeof(p_cursor->'username') is distinct from 'string'
            or not (p_cursor->>'username') collate "C" ~ '^[a-z][a-z0-9_]{2,23}$' then
            raise exception using errcode='22023', message='Invalid social cursor.';
        end if;
        cur_name := p_cursor->>'username';
        if p_view='people' then
            if p_cursor <> jsonb_build_object('username',cur_name) then
                raise exception using errcode='22023', message='Invalid member cursor.';
            end if;
        else
            if not (p_cursor ?& array['username','watched_date','tmdb_id','week_start'])
                or (select count(*) from jsonb_object_keys(p_cursor))<>4
                or jsonb_typeof(p_cursor->'watched_date') is distinct from 'string'
                or not (p_cursor->>'watched_date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                or jsonb_typeof(p_cursor->'week_start') is distinct from 'string'
                or not (p_cursor->>'week_start') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                or jsonb_typeof(p_cursor->'tmdb_id') is distinct from 'number'
                or not (p_cursor->'tmdb_id')::text ~ '^[1-9][0-9]{0,9}$' then
                raise exception using errcode='22023', message='Invalid activity cursor.';
            end if;
            cur_date := p_cursor->>'watched_date';
            perform cur_date::date;
            perform (p_cursor->>'week_start')::date;
            cur_film := (p_cursor->>'tmdb_id')::bigint;
            -- A saved pagination link from a past week starts the current week afresh.
            if (p_cursor->>'week_start')::date <> first_day then
                cur_name := null; cur_date := null; cur_film := null;
            end if;
        end if;
    end if;
    if p_view='people' then
        if search='' then
            select coalesce(jsonb_agg(jsonb_build_object('username',r.username,
                'display_name',r.display_name,'avatar_id',r.avatar_id) order by r.username collate "C"),'[]'::jsonb)
            into entries from (
                select u.username,p.display_name,p.avatar_id
                from mml_private.profiles p join mml_private.usernames u on u.user_id=p.user_id
                where p.is_public and mml_private.name_allowed(u.username) and mml_private.name_allowed(p.display_name)
                    and (cur_name is null or u.username collate "C" > cur_name collate "C")
                order by u.username collate "C" limit cap+1
            ) r;
        else
            select coalesce(jsonb_agg(jsonb_build_object('username',r.username,
                'display_name',r.display_name,'avatar_id',r.avatar_id) order by r.username collate "C"),'[]'::jsonb)
            into entries from (
                select u.username,p.display_name,p.avatar_id
                from (
                    select u1.user_id from mml_private.usernames u1
                    where lower(u1.username) like search_pattern escape E'\\'
                    union
                    select p1.user_id from mml_private.profiles p1
                    where p1.is_public and lower(p1.display_name) like search_pattern escape E'\\'
                ) matched
                join mml_private.profiles p on p.user_id=matched.user_id
                join mml_private.usernames u on u.user_id=matched.user_id
                where p.is_public and mml_private.name_allowed(u.username) and mml_private.name_allowed(p.display_name)
                    and (cur_name is null or u.username collate "C" > cur_name collate "C")
                order by u.username collate "C" limit cap+1
            ) r;
        end if;
    else
        upper_date := least(today::text, coalesce(cur_date, today::text));
        if search='' then
            select coalesce(jsonb_agg(jsonb_build_object('username',r.username,'display_name',r.display_name,
                'avatar_id',r.avatar_id,'tmdb_id',r.tmdb_id,'watched_date',r.watched_date) ||
                case when r.show_ratings and r.rating <> 'null'::jsonb then jsonb_build_object('rating',r.rating)
                    else '{}'::jsonb end order by r.watched_date desc,r.username collate "C",r.tmdb_id),'[]'::jsonb)
            into entries from (
                select u.username,p.display_name,p.avatar_id,p.show_ratings,pick.id tmdb_id,
                    l.data->>'watched_date' watched_date,l.data->'rating' rating
                from public.mml_library l
                join mml_private.profiles p on p.user_id=l.user_id
                join mml_private.usernames u on u.user_id=p.user_id
                cross join lateral unnest(p.tmdb_ids) pick(id)
                where p.is_public and mml_private.name_allowed(u.username) and mml_private.name_allowed(p.display_name)
                    and l.record_key='tmdb:'||pick.id::text
                    and l.data->'deleted_at'='null'::jsonb and l.data->>'status'='Watched'
                    and l.data->>'watched_date' is not null
                    and l.data->>'watched_date' between first_day::text and upper_date
                    and (cur_date is null or l.data->>'watched_date'<cur_date
                        or l.data->>'watched_date'=cur_date and u.username collate "C">cur_name collate "C"
                        or l.data->>'watched_date'=cur_date and u.username=cur_name and pick.id>cur_film)
                order by l.data->>'watched_date' desc,u.username collate "C",pick.id limit cap+1
            ) r;
        else
            select coalesce(jsonb_agg(jsonb_build_object('username',r.username,'display_name',r.display_name,
                'avatar_id',r.avatar_id,'tmdb_id',r.tmdb_id,'watched_date',r.watched_date) ||
                case when r.show_ratings and r.rating <> 'null'::jsonb then jsonb_build_object('rating',r.rating)
                    else '{}'::jsonb end order by r.watched_date desc,r.username collate "C",r.tmdb_id),'[]'::jsonb)
            into entries from (
                select u.username,p.display_name,p.avatar_id,p.show_ratings,pick.id tmdb_id,
                    l.data->>'watched_date' watched_date,l.data->'rating' rating
                from (
                    select u1.user_id from mml_private.usernames u1
                    where lower(u1.username) like search_pattern escape E'\\'
                    union
                    select p1.user_id from mml_private.profiles p1
                    where p1.is_public and lower(p1.display_name) like search_pattern escape E'\\'
                ) matched
                join mml_private.profiles p on p.user_id=matched.user_id
                join mml_private.usernames u on u.user_id=matched.user_id
                cross join lateral unnest(p.tmdb_ids) pick(id)
                join public.mml_library l on l.user_id=p.user_id and l.record_key='tmdb:'||pick.id::text
                where p.is_public and mml_private.name_allowed(u.username) and mml_private.name_allowed(p.display_name)
                    and l.data->'deleted_at'='null'::jsonb and l.data->>'status'='Watched'
                    and l.data->>'watched_date' is not null
                    and l.data->>'watched_date' between first_day::text and upper_date
                    and (cur_date is null or l.data->>'watched_date'<cur_date
                        or l.data->>'watched_date'=cur_date and u.username collate "C">cur_name collate "C"
                        or l.data->>'watched_date'=cur_date and u.username=cur_name and pick.id>cur_film)
                order by l.data->>'watched_date' desc,u.username collate "C",pick.id limit cap+1
            ) r;
        end if;
    end if;
    if jsonb_array_length(entries)>cap then
        select jsonb_agg(v.value order by v.ordinality) into entries
            from jsonb_array_elements(entries) with ordinality v(value,ordinality) where v.ordinality<=cap;
        last_entry := entries->(cap-1);
        next_page := jsonb_build_object('username',last_entry->>'username');
        if p_view='week' then
            next_page := next_page || jsonb_build_object('watched_date',last_entry->>'watched_date',
                'tmdb_id',last_entry->'tmdb_id','week_start',first_day::text);
        end if;
    end if;
    return jsonb_build_object('protocol',1,'view',p_view,'rows',entries,'next_cursor',next_page,
        'week_start',first_day::text,'week_end',(first_day+6)::text);
exception when invalid_text_representation or datetime_field_overflow or sqlstate '22007' then
    raise exception using errcode='22023', message='Invalid social cursor.';
end;
$$;
revoke all on function public.mml_social_page(text,text,jsonb) from public,anon,authenticated;
grant execute on function public.mml_social_page(text,text,jsonb) to anon,authenticated;
notify pgrst,'reload schema';
commit;
