-- Apply after 001/002/003. Registration usernames and TR/EN profile-name rules.
-- Usernames remain immutable. No existing account is renamed, deleted or published.
begin;

create or replace function mml_private.name_allowed(p_value text)
returns boolean language plpgsql immutable security invoker set search_path='' as $$
declare
    normalized text;
    candidate text;
    compact text;
    words text[];
begin
    if p_value is null then return false; end if;
    normalized := replace(lower(normalize(p_value,NFKD) collate "C"),'ı','i');
    normalized := regexp_replace(normalized,'[̀-ͯ]','','g');
    normalized := regexp_replace(normalized,'[^a-z0-9]+','_','g');
    foreach candidate in array array[normalized,translate(normalized,'0134578','oieastb')] loop
        compact := replace(candidate,'_','');
        if compact ~ 'hitler|motherfucker|orospu|siktir|sikeyim|sikim|yarrak|yarak|amcik|gotveren|nigger|faggot' then return false; end if;
        words := string_to_array(btrim(regexp_replace(candidate,'[0-9]+','_','g'),'_'),'_');
        if words && array['amk','aq','asshole','bastard','bitch','bitchboy','cunt','dick','dickhead','fuck','fucker','fuckhead','fucking','fuckoff','fuckyou','nazi','nazifan','nazis','nazism','pussy','shit','shithead','shitty','sik']::text[] or compact=any(array['amk','aq','asshole','bastard','bitch','bitchboy','cunt','dick','dickhead','fuck','fucker','fuckhead','fucking','fuckoff','fuckyou','nazi','nazifan','nazis','nazism','pussy','shit','shithead','shitty','sik']::text[]) then
            return false;
        end if;
    end loop;
    return true;
end;
$$;
revoke all on function mml_private.name_allowed(text) from public,anon,authenticated;

create or replace function mml_private.check_public_name()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
    -- Even an old disallowed name must never prevent privacy revocation.
    if tg_op='UPDATE' and not new.is_public then return new; end if;
    if not mml_private.name_allowed(new.display_name) then
        raise exception using errcode='22023', message='This profile name is not allowed.';
    end if;
    return new;
end;
$$;
revoke all on function mml_private.check_public_name() from public,anon,authenticated;
drop trigger if exists mml_public_name_policy on mml_private.profiles;
create trigger mml_public_name_policy before insert or update of display_name
    on mml_private.profiles for each row execute function mml_private.check_public_name();

create or replace function public.mml_username_protocol()
returns jsonb language sql stable security invoker set search_path='' as $$
    select jsonb_build_object('service','mymovielist-usernames','protocol',2);
$$;
revoke all on function public.mml_username_protocol() from public,anon,authenticated;
grant execute on function public.mml_username_protocol() to anon,authenticated;

create or replace function public.mml_claim_username(p_username text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    owner_id uuid := auth.uid();
    chosen text := lower(btrim(p_username) collate "C");
    current_name text;
begin
    if owner_id is null then
        raise exception using errcode='42501', message='Sign in before choosing a username.';
    end if;
    if chosen is null or char_length(chosen)>24
       or not chosen collate "C" ~ '^[a-z][a-z0-9_]{2,23}$'
       or chosen in ('admin','administrator','api','auth','support','root','system',
            'myshelf','mymovielist','myserieslist','mygamelist','account','settings',
            'login','logout','register','signup','signin','profile','profiles','help',
            'about','official','null','undefined') then
        raise exception using errcode='22023', message='Choose a valid username.';
    end if;
    if not mml_private.name_allowed(chosen) then
        raise exception using errcode='22023', message='This name is not allowed.';
    end if;
    -- Both unique indexes arbitrate simultaneous requests atomically. No
    -- check-then-insert race and no client-supplied owner ID or metadata trust.
    insert into mml_private.usernames(user_id,username) values(owner_id,chosen)
        on conflict do nothing;
    select u.username into current_name from mml_private.usernames u where u.user_id=owner_id;
    return jsonb_build_object('status',case when current_name=chosen then 'claimed'
        when current_name is not null then 'locked' else 'taken' end,
        'username',current_name);
end;
$$;
revoke all on function public.mml_claim_username(text) from public, anon, authenticated;
grant execute on function public.mml_claim_username(text) to authenticated;



create or replace function public.mml_public_profile(p_share_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    profile mml_private.profiles%rowtype;
    films jsonb;
    counts jsonb;
    result jsonb;
begin
    select * into profile from mml_private.profiles p where p.share_id=p_share_id and p.is_public and mml_private.name_allowed(p.display_name)
        and not exists (select 1 from mml_private.usernames u
            where u.user_id=p.user_id and not mml_private.name_allowed(u.username));
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
