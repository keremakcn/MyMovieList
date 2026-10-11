-- Apply after 001–006. Private actor/director favorites; existing films and
-- public showcases are unchanged. No photo, name or biography is uploaded.
begin;

create table if not exists mml_private.person_favorite_heads (
    user_id uuid primary key references auth.users(id) on delete cascade,
    revision bigint not null default 0 check (revision >= 0)
);
create table if not exists mml_private.person_favorites (
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('actor','director')),
    person_id bigint not null check (person_id between 1 and 9999999999),
    favorite boolean not null,
    edited_at timestamptz not null,
    revision bigint not null check (revision > 0),
    primary key (user_id,role,person_id),
    unique (user_id,revision)
);
create table if not exists mml_private.person_favorite_receipts (
    user_id uuid not null references auth.users(id) on delete cascade,
    operation_id uuid not null,
    request_hash text not null,
    result jsonb not null,
    primary key (user_id,operation_id)
);
alter table mml_private.person_favorite_heads enable row level security;
alter table mml_private.person_favorites enable row level security;
alter table mml_private.person_favorite_receipts enable row level security;
revoke all on mml_private.person_favorite_heads,mml_private.person_favorites,
    mml_private.person_favorite_receipts from public,anon,authenticated;

create or replace function public.mml_write_person_favorite(
    p_operation_id uuid,p_role text,p_person_id bigint,p_favorite boolean,p_edited_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
    owner_id uuid := auth.uid();
    previous mml_private.person_favorites%rowtype;
    receipt mml_private.person_favorite_receipts%rowtype;
    request_hash text;
    next_revision bigint;
    response jsonb;
begin
    if owner_id is null then
        raise exception using errcode='42501',message='Sign in before changing person favorites.';
    end if;
    if p_operation_id is null or p_role is null or p_role not in ('actor','director')
       or p_person_id is null or p_person_id not between 1 and 9999999999
       or p_favorite is null or p_edited_at is null or not isfinite(p_edited_at)
       or p_edited_at < '1970-01-01T00:00:00Z'::timestamptz
       or p_edited_at > clock_timestamp()+interval '5 minutes' then
        raise exception using errcode='22023',message='Invalid person favorite.';
    end if;
    request_hash := encode(sha256(convert_to(jsonb_build_object('role',p_role,
        'person_id',p_person_id,'favorite',p_favorite,'edited_at',p_edited_at)::text,'UTF8')),'hex');
    insert into mml_private.person_favorite_heads(user_id) values(owner_id) on conflict do nothing;
    -- One owner lock serializes receipts, revisions and concurrent pulls.
    perform 1 from mml_private.person_favorite_heads h where h.user_id=owner_id for update;
    select * into receipt from mml_private.person_favorite_receipts r
        where r.user_id=owner_id and r.operation_id=p_operation_id;
    if found then
        if receipt.request_hash<>request_hash then
            raise exception using errcode='22023',message='Operation ID was reused.';
        end if;
        return receipt.result;
    end if;
    select * into previous from mml_private.person_favorites f
        where f.user_id=owner_id and f.role=p_role and f.person_id=p_person_id;
    if not found or p_edited_at>previous.edited_at then
        if previous.user_id is null and (select count(*) from mml_private.person_favorites f
            where f.user_id=owner_id)>=10000 then
            raise exception using errcode='22023',message='Your person favorites list is full.';
        end if;
        update mml_private.person_favorite_heads h set revision=h.revision+1
            where h.user_id=owner_id returning h.revision into next_revision;
        insert into mml_private.person_favorites(user_id,role,person_id,favorite,edited_at,revision)
            values(owner_id,p_role,p_person_id,p_favorite,p_edited_at,next_revision)
            on conflict(user_id,role,person_id) do update set
            favorite=excluded.favorite,edited_at=excluded.edited_at,revision=excluded.revision
            returning * into previous;
    end if;
    -- Equal timestamps retain the server decision. False rows are tombstones:
    -- an older offline "favorite" can never resurrect a newer removal.
    response := jsonb_build_object('status','applied','record',jsonb_build_object(
        'role',previous.role,'person_id',previous.person_id,'favorite',previous.favorite,
        'edited_at',previous.edited_at,'revision',previous.revision));
    insert into mml_private.person_favorite_receipts values(owner_id,p_operation_id,request_hash,response);
    return response;
end;
$$;
revoke all on function public.mml_write_person_favorite(uuid,text,bigint,boolean,timestamptz)
    from public,anon,authenticated;
grant execute on function public.mml_write_person_favorite(uuid,text,bigint,boolean,timestamptz)
    to authenticated;

create or replace function public.mml_pull_person_favorites(p_cursor bigint default 0,p_limit integer default 100)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
    owner_id uuid := auth.uid();
    head bigint;
    changes jsonb;
    next_cursor bigint;
begin
    if owner_id is null then
        raise exception using errcode='42501',message='Sign in before reading person favorites.';
    end if;
    if p_cursor is null or p_cursor<0 or p_limit is null or p_limit not between 1 and 100 then
        raise exception using errcode='22023',message='Invalid person favorites cursor.';
    end if;
    insert into mml_private.person_favorite_heads(user_id) values(owner_id) on conflict do nothing;
    select h.revision into head from mml_private.person_favorite_heads h where h.user_id=owner_id for share;
    if p_cursor>head then
        raise exception using errcode='22023',message='Invalid person favorites cursor.';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('role',f.role,'person_id',f.person_id,
        'favorite',f.favorite,'edited_at',f.edited_at,'revision',f.revision) order by f.revision),'[]'::jsonb),
        coalesce(max(f.revision),p_cursor) into changes,next_cursor from (
        select * from mml_private.person_favorites where user_id=owner_id and revision>p_cursor
        order by revision limit p_limit
    ) f;
    return jsonb_build_object('protocol',1,'changes',changes,'cursor',next_cursor);
end;
$$;
revoke all on function public.mml_pull_person_favorites(bigint,integer) from public,anon,authenticated;
grant execute on function public.mml_pull_person_favorites(bigint,integer) to authenticated;

create or replace function public.mml_person_favorites_protocol()
returns jsonb language sql stable set search_path='' as $$
    select jsonb_build_object('service','mymovielist-person-favorites','protocol',1);
$$;
revoke all on function public.mml_person_favorites_protocol() from public,anon,authenticated;
grant execute on function public.mml_person_favorites_protocol() to anon,authenticated;
notify pgrst,'reload schema';
commit;
