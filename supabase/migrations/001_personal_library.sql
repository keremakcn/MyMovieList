-- MyMovieList cloud protocol v1. Run as postgres in Supabase SQL Editor.
-- No account or device-library data is copied by this migration.
-- Re-running this file keeps all existing records and receipts.
begin;

create schema if not exists mml_private;
revoke all on schema mml_private from public, anon, authenticated;

create table if not exists public.mml_library (
    user_id uuid not null references auth.users(id) on delete cascade,
    record_key text not null,
    data jsonb not null,
    revision bigint not null check (revision > 0),
    changed_at timestamptz not null default now(),
    primary key (user_id, record_key),
    constraint mml_library_key check (
        record_key ~ '^tmdb:[1-9][0-9]{0,9}$'
        or record_key ~ '^custom:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ),
    constraint mml_library_data_object check (jsonb_typeof(data) = 'object')
);
create unique index if not exists mml_library_revision
    on public.mml_library(user_id, revision);

-- One locked revision counter per user ensures commit order cannot skip changes.
-- Neither counters nor operation receipts are exposed through the Data API.
create table if not exists mml_private.sync_heads (
    user_id uuid primary key references auth.users(id) on delete cascade,
    revision bigint not null default 0 check (revision >= 0)
);
create table if not exists mml_private.sync_receipts (
    user_id uuid not null references auth.users(id) on delete cascade,
    operation_id uuid not null,
    request_hash text not null,
    record_key text not null,
    revision bigint not null,
    created_at timestamptz not null default now(),
    primary key (user_id, operation_id)
);

alter table public.mml_library enable row level security;
alter table mml_private.sync_heads enable row level security;
alter table mml_private.sync_receipts enable row level security;
revoke all on public.mml_library from public, anon, authenticated;
revoke all on mml_private.sync_heads, mml_private.sync_receipts
    from public, anon, authenticated;
grant usage on schema public to anon, authenticated;
grant select on public.mml_library to authenticated;
drop policy if exists mml_library_owner_read on public.mml_library;
create policy mml_library_owner_read on public.mml_library
    for select to authenticated using ((select auth.uid()) = user_id);

-- Writes go through the revision-checked RPC. Do not grant direct INSERT,
-- UPDATE or DELETE: hard deletion could resurrect a film from an offline device.
create or replace function mml_private.validate_record(p_key text, p_data jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
declare
    allowed text[] := array['status','rating','note','favorite','watched_date',
                            'added_at','order_key','deleted_at','custom'];
    item text;
begin
    if p_key is null or not (
        p_key ~ '^tmdb:[1-9][0-9]{0,9}$' or
        p_key ~ '^custom:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ) then
        raise exception using errcode = '22023', message = 'Invalid movie identity.';
    end if;
    if p_data is null or jsonb_typeof(p_data) <> 'object'
       or octet_length(p_data::text) > 150000 then
        raise exception using errcode = '22023', message = 'Invalid personal record.';
    end if;
    if not (p_data ?& allowed) or exists (
        select 1 from jsonb_object_keys(p_data) as k(name)
        where not k.name = any(allowed)
    ) then
        raise exception using errcode = '22023', message = 'Unexpected personal record fields.';
    end if;
    if jsonb_typeof(p_data->'status') <> 'string'
       or p_data->>'status' not in ('Watchlist','Watched')
       or jsonb_typeof(p_data->'favorite') <> 'boolean' then
        raise exception using errcode = '22023', message = 'Invalid status or favorite.';
    end if;
    if p_data->'rating' <> 'null'::jsonb and (
        jsonb_typeof(p_data->'rating') <> 'number'
        or not (p_data->>'rating') ~ '^(10|[1-9])$'
    ) then
        raise exception using errcode = '22023', message = 'Rating must be from 1 to 10.';
    end if;
    if p_data->'note' <> 'null'::jsonb and (
        jsonb_typeof(p_data->'note') <> 'string'
        or char_length(p_data->>'note') > 20000
    ) then
        raise exception using errcode = '22023', message = 'Note exceeds 20,000 characters.';
    end if;
    if p_data->'watched_date' <> 'null'::jsonb then
        if jsonb_typeof(p_data->'watched_date') <> 'string'
           or not (p_data->>'watched_date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
            raise exception using errcode = '22023', message = 'Invalid watched date.';
        end if;
        perform (p_data->>'watched_date')::date;
    end if;
    foreach item in array array['added_at','deleted_at'] loop
        if item = 'deleted_at' and p_data->item = 'null'::jsonb then
            continue;
        end if;
        if jsonb_typeof(p_data->item) <> 'string'
           or not (p_data->>item) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' then
            raise exception using errcode = '22023', message = 'Invalid record timestamp.';
        end if;
        perform (p_data->>item)::timestamptz;
    end loop;
    if jsonb_typeof(p_data->'order_key') <> 'string'
       or not (p_data->>'order_key') ~ '^[0-9]{20}:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then
        raise exception using errcode = '22023', message = 'Invalid original library order.';
    end if;
    if p_key like 'tmdb:%' then
        if p_data->'custom' <> 'null'::jsonb then
            raise exception using errcode = '22023', message = 'Catalog metadata is not stored in the cloud.';
        end if;
    else
        if jsonb_typeof(p_data->'custom') <> 'object' or not (
            p_data->'custom' ?& array['title','year','genre']
        ) then
            raise exception using errcode = '22023', message = 'Custom film fields are required.';
        end if;
        if exists (select 1 from jsonb_object_keys(p_data->'custom') as k(name)
                   where k.name not in ('title','year','genre')) then
            raise exception using errcode = '22023', message = 'Unexpected custom film fields.';
        end if;
        if jsonb_typeof(p_data->'custom'->'title') <> 'string'
           or char_length(btrim(p_data->'custom'->>'title')) not between 1 and 300 then
            raise exception using errcode = '22023', message = 'Invalid custom film title.';
        end if;
        if p_data->'custom'->'year' <> 'null'::jsonb and (
            jsonb_typeof(p_data->'custom'->'year') <> 'number'
            or not (p_data->'custom'->>'year') ~ '^[0-9]{4}$'
        ) then
            raise exception using errcode = '22023', message = 'Invalid custom film year.';
        end if;
        if (p_data->'custom'->>'year')::integer not between 1800 and 2200 then
            raise exception using errcode = '22023', message = 'Invalid custom film year.';
        end if;
        if p_data->'custom'->'genre' <> 'null'::jsonb and (
            jsonb_typeof(p_data->'custom'->'genre') <> 'string'
            or char_length(p_data->'custom'->>'genre') > 300
        ) then
            raise exception using errcode = '22023', message = 'Invalid custom film genre.';
        end if;
    end if;
exception
    when invalid_text_representation or datetime_field_overflow
         or sqlstate '22007' then
        raise exception using errcode = '22023', message = 'Invalid personal record value.';
end;
$$;
revoke all on function mml_private.validate_record(text,jsonb)
    from public, anon, authenticated;

create or replace function public.mml_cloud_status()
returns jsonb language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object('service','mymovielist-sync','protocol',1);
$$;
revoke all on function public.mml_cloud_status() from public, anon, authenticated;
grant execute on function public.mml_cloud_status() to anon, authenticated;

create or replace function public.mml_push_change(
    p_operation_id uuid, p_record_key text, p_expected_revision bigint, p_data jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    owner_id uuid := auth.uid();
    existing public.mml_library%rowtype;
    receipt mml_private.sync_receipts%rowtype;
    request_hash text;
    next_revision bigint;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Sign in before syncing.';
    end if;
    if p_operation_id is null or p_expected_revision is null or p_expected_revision < 0 then
        raise exception using errcode = '22023', message = 'Invalid sync operation.';
    end if;
    perform mml_private.validate_record(p_record_key, p_data);
    request_hash := encode(sha256(convert_to(jsonb_build_object('key',p_record_key,
                            'expected',p_expected_revision,'data',p_data)::text,'UTF8')),'hex');
    insert into mml_private.sync_heads(user_id) values (owner_id)
        on conflict (user_id) do nothing;
    perform 1 from mml_private.sync_heads h where h.user_id = owner_id for update;
    select * into receipt from mml_private.sync_receipts r
        where r.user_id = owner_id and r.operation_id = p_operation_id;
    if found then
        if receipt.request_hash <> request_hash then
            raise exception using errcode = '22023', message = 'Operation ID was reused with different data.';
        end if;
        return jsonb_build_object('status','applied','record_key',receipt.record_key,
                                 'revision',receipt.revision,'replayed',true);
    end if;
    select * into existing from public.mml_library l
        where l.user_id = owner_id and l.record_key = p_record_key;
    if coalesce(existing.revision,0) <> p_expected_revision then
        return jsonb_build_object('status','conflict','record_key',p_record_key,
            'remote',case when existing.revision is null then null
                else jsonb_build_object('data',existing.data,'revision',existing.revision) end);
    end if;
    -- A film's addition time and ordering survive edits, deletion and Undo.
    if existing.revision is not null and (
        p_data->'added_at' is distinct from existing.data->'added_at'
        or p_data->'order_key' is distinct from existing.data->'order_key'
    ) then
        raise exception using errcode = '22023', message = 'Original addition time and order cannot change.';
    end if;
    update mml_private.sync_heads h set revision = h.revision + 1
        where h.user_id = owner_id returning revision into next_revision;
    insert into public.mml_library(user_id,record_key,data,revision,changed_at)
        values (owner_id,p_record_key,p_data,next_revision,clock_timestamp())
        on conflict (user_id,record_key) do update
        set data = excluded.data, revision = excluded.revision,
            changed_at = excluded.changed_at;
    insert into mml_private.sync_receipts(user_id,operation_id,request_hash,record_key,revision)
        values (owner_id,p_operation_id,request_hash,p_record_key,next_revision);
    return jsonb_build_object('status','applied','record_key',p_record_key,
                             'revision',next_revision,'replayed',false);
end;
$$;
revoke all on function public.mml_push_change(uuid,text,bigint,jsonb)
    from public, anon, authenticated;
grant execute on function public.mml_push_change(uuid,text,bigint,jsonb) to authenticated;

create or replace function public.mml_pull_changes(p_cursor bigint default 0, p_limit integer default 100)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    owner_id uuid := auth.uid();
    changes jsonb;
    head bigint;
    next_cursor bigint;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Sign in before syncing.';
    end if;
    if p_cursor is null or p_cursor < 0 or p_limit is null or p_limit < 1 or p_limit > 200 then
        raise exception using errcode = '22023', message = 'Invalid sync page.';
    end if;
    select coalesce((select h.revision from mml_private.sync_heads h where h.user_id=owner_id),0)
        into head;
    if p_cursor > head then
        raise exception using errcode = '22023', message = 'Cloud history changed; reconcile before syncing.';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('record_key',r.record_key,'data',r.data,
                                              'revision',r.revision) order by r.revision),'[]'::jsonb),
           coalesce(max(r.revision),p_cursor)
        into changes,next_cursor
        from (select l.record_key,l.data,l.revision from public.mml_library l
              where l.user_id=owner_id and l.revision>p_cursor
              order by l.revision limit p_limit) r;
    return jsonb_build_object('protocol',1,'changes',changes,'cursor',next_cursor);
end;
$$;
revoke all on function public.mml_pull_changes(bigint,integer) from public, anon, authenticated;
grant execute on function public.mml_pull_changes(bigint,integer) to authenticated;

notify pgrst, 'reload schema';
commit;
