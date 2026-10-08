-- Apply after 001 and 002. No account is renamed or made public automatically.
-- A handle is chosen once; display names and avatars remain editable.
begin;

create table if not exists mml_private.usernames (
    user_id uuid primary key references auth.users(id) on delete cascade,
    username text not null unique,
    created_at timestamptz not null default now(),
    constraint mml_username_format check (
        username collate "C" ~ '^[a-z][a-z0-9_]{2,23}$'
        and username not in ('admin','administrator','api','auth','support','root','system',
            'myshelf','mymovielist','myserieslist','mygamelist','account','settings',
            'login','logout','register','signup','signin','profile','profiles','help',
            'about','official','null','undefined')
    )
);
alter table mml_private.usernames enable row level security;
revoke all on mml_private.usernames from public, anon, authenticated;

create or replace function public.mml_username_status()
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then
        raise exception using errcode='42501', message='Sign in before choosing a username.';
    end if;
    return jsonb_build_object('username',(
        select u.username from mml_private.usernames u where u.user_id=auth.uid()
    ));
end;
$$;
revoke all on function public.mml_username_status() from public, anon, authenticated;
grant execute on function public.mml_username_status() to authenticated;

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

create or replace function public.mml_public_profile_by_username(p_username text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
    chosen text := lower(btrim(p_username) collate "C");
    share uuid;
    projection jsonb;
begin
    if chosen is null or char_length(chosen)>24
        or not chosen collate "C" ~ '^[a-z][a-z0-9_]{2,23}$' then
        return jsonb_build_object('found',false);
    end if;
    select p.share_id into share from mml_private.usernames u
        join mml_private.profiles p on p.user_id=u.user_id
        where u.username=chosen and p.is_public;
    if share is null then return jsonb_build_object('found',false); end if;
    projection := public.mml_public_profile(share);
    if not (projection->>'found')::boolean then return projection; end if;
    return projection || jsonb_build_object('username',chosen);
end;
$$;
revoke all on function public.mml_public_profile_by_username(text) from public, anon, authenticated;
grant execute on function public.mml_public_profile_by_username(text) to anon, authenticated;

-- Existing UUID links and RPCs deliberately retain their existing contracts.
notify pgrst, 'reload schema';
commit;
