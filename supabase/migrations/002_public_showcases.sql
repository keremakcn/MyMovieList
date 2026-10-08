-- Opt-in public showcases. Apply after 001_personal_library.sql.
-- Existing accounts remain private. Private library permissions are unchanged.
begin;

create table if not exists mml_private.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    share_id uuid not null unique default gen_random_uuid(),
    is_public boolean not null default false,
    revision bigint not null default 0 check (revision >= 0),
    display_name text not null default '',
    avatar_id text not null default 'cat-luna',
    tmdb_ids bigint[] not null default '{}',
    show_ratings boolean not null default false,
    show_stats boolean not null default false,
    last_operation uuid,
    last_hash text,
    updated_at timestamptz not null default now(),
    constraint mml_profile_name check (char_length(display_name) <= 40),
    constraint mml_profile_films check (cardinality(tmdb_ids) <= 6)
);
alter table mml_private.profiles enable row level security;
revoke all on mml_private.profiles from public, anon, authenticated;

create or replace function mml_private.profile_settings(p_user uuid)
returns jsonb language sql stable security invoker set search_path = '' as $$
    select coalesce((select jsonb_build_object('share_id',p.share_id,
        'is_public',p.is_public,'revision',p.revision)
        from mml_private.profiles p where p.user_id=p_user),
        jsonb_build_object('share_id',null,'is_public',false,'revision',0));
$$;
revoke all on function mml_private.profile_settings(uuid) from public, anon, authenticated;

create or replace function public.mml_sharing_status()
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then
        raise exception using errcode='42501', message='Sign in before changing sharing.';
    end if;
    return mml_private.profile_settings(auth.uid());
end;
$$;
revoke all on function public.mml_sharing_status() from public, anon, authenticated;
grant execute on function public.mml_sharing_status() to authenticated;

create or replace function public.mml_write_showcase(
    p_operation_id uuid, p_expected_revision bigint, p_action text, p_payload jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    owner_id uuid := auth.uid();
    current_profile mml_private.profiles%rowtype;
    request_hash text;
    ids bigint[];
    allowed text[] := array['display_name','avatar_id','tmdb_ids','show_ratings','show_stats'];
begin
    if owner_id is null then
        raise exception using errcode='42501', message='Sign in before changing sharing.';
    end if;
    if p_operation_id is null or p_expected_revision is null or p_expected_revision<0
       or p_action is null or p_action not in ('publish','update','unpublish')
       or p_payload is null or jsonb_typeof(p_payload)<>'object'
       or octet_length(p_payload::text)>4096 then
        raise exception using errcode='22023', message='Invalid showcase operation.';
    end if;
    if p_action='unpublish' then
        if p_payload<>'{}'::jsonb then
            raise exception using errcode='22023', message='Invalid privacy operation.';
        end if;
    else
        if not (p_payload ?& allowed) or exists (
            select 1 from jsonb_object_keys(p_payload) k(name) where not k.name=any(allowed)
        ) or jsonb_typeof(p_payload->'display_name')<>'string'
          or char_length(p_payload->>'display_name')>40
          or (p_payload->>'display_name') ~ '[[:cntrl:]]'
          or jsonb_typeof(p_payload->'avatar_id')<>'string'
          or p_payload->>'avatar_id' not in ('cat-luna','cat-cocoa','cat-sunshine','cat-sage',
            'cat-coral','cat-cloud','cat-midnight','cat-peach','cat-sky','cat-mocha',
            'cat-lilac','cat-mint','cat-cherry','cat-gold','cat-ocean','cat-silver')
          or jsonb_typeof(p_payload->'tmdb_ids')<>'array'
          or jsonb_typeof(p_payload->'show_ratings')<>'boolean'
          or jsonb_typeof(p_payload->'show_stats')<>'boolean' then
            raise exception using errcode='22023', message='Invalid showcase fields.';
        end if;
        if jsonb_array_length(p_payload->'tmdb_ids')>6 or exists (
            select 1 from jsonb_array_elements(p_payload->'tmdb_ids') v(value)
            where jsonb_typeof(v.value)<>'number' or not v.value::text ~ '^[1-9][0-9]{0,9}$'
        ) then
            raise exception using errcode='22023', message='Choose up to six catalog films.';
        end if;
        select coalesce(array_agg(v.value::text::bigint order by v.ordinality),'{}'::bigint[])
            into ids from jsonb_array_elements(p_payload->'tmdb_ids') with ordinality v(value,ordinality);
        if cardinality(ids)<>(select count(distinct id) from unnest(ids) id)
          or exists (select 1 from unnest(ids) id where not exists (
            select 1 from public.mml_library l where l.user_id=owner_id and l.record_key='tmdb:'||id::text
          )) then
            raise exception using errcode='22023', message='Choose films from your own synced library.';
        end if;
    end if;
    request_hash := encode(sha256(convert_to(jsonb_build_object('action',p_action,
        'expected',p_expected_revision,'payload',p_payload)::text,'UTF8')),'hex');
    insert into mml_private.profiles(user_id) values (owner_id) on conflict (user_id) do nothing;
    select * into current_profile from mml_private.profiles p where p.user_id=owner_id for update;
    if current_profile.last_operation=p_operation_id then
        if current_profile.last_hash<>request_hash then
            raise exception using errcode='22023', message='Operation ID was reused.';
        end if;
        return jsonb_build_object('status','applied','settings',mml_private.profile_settings(owner_id));
    end if;
    -- Privacy-off always wins; ordinary updates can never publish a private row.
    if p_action<>'unpublish' and (current_profile.revision<>p_expected_revision
        or (p_action='update' and not current_profile.is_public)) then
        return jsonb_build_object('status','conflict','settings',mml_private.profile_settings(owner_id));
    end if;
    update mml_private.profiles p set
        is_public=case when p_action='publish' then true when p_action='unpublish' then false else p.is_public end,
        display_name=case when p_action='unpublish' then p.display_name else p_payload->>'display_name' end,
        avatar_id=case when p_action='unpublish' then p.avatar_id else p_payload->>'avatar_id' end,
        tmdb_ids=case when p_action='unpublish' then p.tmdb_ids else ids end,
        show_ratings=case when p_action='unpublish' then p.show_ratings else (p_payload->>'show_ratings')::boolean end,
        show_stats=case when p_action='unpublish' then p.show_stats else (p_payload->>'show_stats')::boolean end,
        revision=p.revision+1, last_operation=p_operation_id, last_hash=request_hash, updated_at=clock_timestamp()
        where p.user_id=owner_id;
    return jsonb_build_object('status','applied','settings',mml_private.profile_settings(owner_id));
end;
$$;
revoke all on function public.mml_write_showcase(uuid,bigint,text,jsonb) from public, anon, authenticated;
grant execute on function public.mml_write_showcase(uuid,bigint,text,jsonb) to authenticated;

create or replace function public.mml_public_profile(p_share_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    profile mml_private.profiles%rowtype;
    films jsonb;
    counts jsonb;
    result jsonb;
begin
    select * into profile from mml_private.profiles p where p.share_id=p_share_id and p.is_public;
    if not found then return jsonb_build_object('found',false); end if;
    -- Build a strict public projection. Never return library rows or Auth metadata.
    select coalesce(jsonb_agg(jsonb_build_object('tmdb_id',pick.id) ||
        case when profile.show_ratings and l.data->'rating'<>'null'::jsonb
             then jsonb_build_object('rating',l.data->'rating') else '{}'::jsonb end
        order by pick.ordinality),'[]'::jsonb) into films
    from unnest(profile.tmdb_ids) with ordinality pick(id,ordinality)
    join public.mml_library l on l.user_id=profile.user_id and l.record_key='tmdb:'||pick.id::text
    where l.data->'deleted_at'='null'::jsonb;
    result := jsonb_build_object('found',true,'share_id',profile.share_id,
        'display_name',profile.display_name,'avatar_id',profile.avatar_id,'films',films);
    if profile.show_stats then
        select jsonb_build_object('total',count(*),
            'watched',count(*) filter (where l.data->>'status'='Watched'),
            'favorites',count(*) filter (where l.data->'favorite'='true'::jsonb),
            'watchlist',count(*) filter (where l.data->>'status'='Watchlist')) into counts
            from public.mml_library l where l.user_id=profile.user_id and l.data->'deleted_at'='null'::jsonb;
        result := result || jsonb_build_object('counts',counts);
    end if;
    return result;
end;
$$;
revoke all on function public.mml_public_profile(uuid) from public, anon, authenticated;
grant execute on function public.mml_public_profile(uuid) to anon, authenticated;

notify pgrst,'reload schema';
commit;
