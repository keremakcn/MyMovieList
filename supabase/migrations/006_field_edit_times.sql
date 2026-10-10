-- Apply after 001–005. Additive field timestamps for web/desktop/mobile sync.
-- Existing private records, immutable IDs, receipts, RLS and old RPCs survive.
-- Old records keep unknown edit times; no timestamps are fabricated.
begin;
alter table public.mml_library add column if not exists field_versions jsonb not null default '{}'::jsonb;

create or replace function mml_private.validate_field_versions(p_versions jsonb)
returns void language plpgsql security invoker set search_path='' as $$
declare item record;
begin
    if jsonb_typeof(p_versions)<>'object' or octet_length(p_versions::text)>2048 then
        raise exception using errcode='22023', message='Invalid field edit times.';
    end if;
    for item in select key,value from jsonb_each(p_versions) loop
        if item.key not in ('status','rating','note','favorite','watched_date','deleted_at','custom')
          or jsonb_typeof(item.value)<>'string'
          or not (item.value #>> '{}') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' then
            raise exception using errcode='22023', message='Invalid field edit time.';
        end if;
        perform (item.value #>> '{}')::timestamptz;
    end loop;
exception when invalid_text_representation or datetime_field_overflow or sqlstate '22007' then
    raise exception using errcode='22023', message='Invalid field edit time.';
end;
$$;
revoke all on function mml_private.validate_field_versions(jsonb) from public,anon,authenticated;

create or replace function public.mml_time_sync_status()
returns jsonb language sql volatile security invoker set search_path='' as $$
    select jsonb_build_object('service','mymovielist-field-sync','protocol',1,
        'server_time',to_char(clock_timestamp() at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'));
$$;
revoke all on function public.mml_time_sync_status() from public,anon,authenticated;
grant execute on function public.mml_time_sync_status() to anon,authenticated;

create or replace function public.mml_push_change_timed(
    p_operation_id uuid, p_record_key text, p_expected_revision bigint, p_data jsonb, p_field_versions jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    owner_id uuid := auth.uid();
    existing public.mml_library%rowtype;
    receipt mml_private.sync_receipts%rowtype;
    request_hash text;
    next_revision bigint;
    accepted_versions jsonb;
    changed_field text;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Sign in before syncing.';
    end if;
    if p_operation_id is null or p_expected_revision is null or p_expected_revision < 0 then
        raise exception using errcode = '22023', message = 'Invalid sync operation.';
    end if;
    perform mml_private.validate_record(p_record_key, p_data);
    if p_field_versions is not null then
        perform mml_private.validate_field_versions(p_field_versions);
    end if;
    request_hash := encode(sha256(convert_to(jsonb_build_object('key',p_record_key,
                            'expected',p_expected_revision,'data',p_data)::text,'UTF8')),'hex');
    if p_field_versions is not null then
        request_hash := encode(sha256(convert_to(jsonb_build_object('key',p_record_key,
            'expected',p_expected_revision,'data',p_data,'field_versions',p_field_versions)::text,'UTF8')),'hex');
    end if;
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
                else jsonb_build_object('data',existing.data,'revision',existing.revision,'field_versions',existing.field_versions) end);
    end if;
    -- A film's addition time and ordering survive edits, deletion and Undo.
    if existing.revision is not null and (
        p_data->'added_at' is distinct from existing.data->'added_at'
        or p_data->'order_key' is distinct from existing.data->'order_key'
    ) then
        raise exception using errcode = '22023', message = 'Original addition time and order cannot change.';
    end if;
    accepted_versions := coalesce(p_field_versions,existing.field_versions,'{}'::jsonb);
    if p_field_versions is null then
        -- An old client supplies no reliable edit time. Clear only the clocks
        -- of fields it changed, retaining timestamps for untouched fields.
        foreach changed_field in array array['status','rating','note','favorite','watched_date','deleted_at','custom'] loop
            if existing.revision is null or p_data->changed_field is distinct from existing.data->changed_field then
                accepted_versions := accepted_versions - changed_field;
            end if;
        end loop;
    end if;
    update mml_private.sync_heads h set revision = h.revision + 1
        where h.user_id = owner_id returning revision into next_revision;
    insert into public.mml_library(user_id,record_key,data,revision,changed_at,field_versions)
        values (owner_id,p_record_key,p_data,next_revision,clock_timestamp(),accepted_versions)
        on conflict (user_id,record_key) do update
        set data = excluded.data, revision = excluded.revision,
            changed_at = excluded.changed_at, field_versions = excluded.field_versions;
    insert into mml_private.sync_receipts(user_id,operation_id,request_hash,record_key,revision)
        values (owner_id,p_operation_id,request_hash,p_record_key,next_revision);
    return jsonb_build_object('status','applied','record_key',p_record_key,
                             'revision',next_revision,'replayed',false);
end;
$$;
revoke all on function public.mml_push_change_timed(uuid,text,bigint,jsonb,jsonb)
    from public, anon, authenticated;
grant execute on function public.mml_push_change_timed(uuid,text,bigint,jsonb,jsonb) to authenticated;

-- Owner-only editor state. Public profile projections remain unchanged.
create or replace function public.mml_showcase_owner_status()
returns jsonb language plpgsql stable security definer set search_path='' as $$
begin
    if auth.uid() is null then
        raise exception using errcode='42501',message='Sign in before changing sharing.';
    end if;
    return mml_private.profile_settings(auth.uid()) || jsonb_build_object('owner_settings',
        coalesce((select jsonb_build_object('tmdb_ids',p.tmdb_ids,'show_ratings',p.show_ratings,
            'show_stats',p.show_stats) from mml_private.profiles p where p.user_id=auth.uid()),
            jsonb_build_object('tmdb_ids','[]'::jsonb,'show_ratings',false,'show_stats',false)));
end;
$$;
revoke all on function public.mml_showcase_owner_status() from public,anon,authenticated;
grant execute on function public.mml_showcase_owner_status() to authenticated;

-- Retain the original v1 endpoint and its exact payload/receipt contract.
create or replace function public.mml_push_change(
    p_operation_id uuid,p_record_key text,p_expected_revision bigint,p_data jsonb
) returns jsonb language sql security definer set search_path='' as $$
    select public.mml_push_change_timed(p_operation_id,p_record_key,p_expected_revision,p_data,null);
$$;
revoke all on function public.mml_push_change(uuid,text,bigint,jsonb) from public,anon,authenticated;
grant execute on function public.mml_push_change(uuid,text,bigint,jsonb) to authenticated;

create or replace function public.mml_pull_changes_timed(p_cursor bigint default 0, p_limit integer default 100)
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
                                              'revision',r.revision,'field_versions',r.field_versions) order by r.revision),'[]'::jsonb),
           coalesce(max(r.revision),p_cursor)
        into changes,next_cursor
        from (select l.record_key,l.data,l.revision,l.field_versions from public.mml_library l
              where l.user_id=owner_id and l.revision>p_cursor
              order by l.revision limit p_limit) r;
    return jsonb_build_object('protocol',1,'changes',changes,'cursor',next_cursor);
end;
$$;
revoke all on function public.mml_pull_changes_timed(bigint,integer) from public, anon, authenticated;
grant execute on function public.mml_pull_changes_timed(bigint,integer) to authenticated;

notify pgrst,'reload schema';
commit;
