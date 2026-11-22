import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';

const require = createRequire(process.env.PGLITE_TEST_RUNTIME || import.meta.url);
const {PGlite} = require('@electric-sql/pglite');
const {pg_trgm} = require('@electric-sql/pglite/contrib/pg_trgm');

const MIGRATIONS = [
  '001_personal_library.sql',
  '002_public_showcases.sql',
  '003_unique_usernames.sql',
  '004_registration_usernames.sql',
  '005_social_discovery.sql',
  '006_field_edit_times.sql',
  '007_person_favorites.sql',
  '008_social_scale_indexes.sql',
];
const sqlByFile = Object.fromEntries(
  await Promise.all(MIGRATIONS.map(async f => [f, await readFile(new URL('../migrations/' + f, import.meta.url), 'utf8')])),
);
const uid = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const shift = (day, delta) => new Date(Date.parse(day + 'T12:00:00Z') + delta * 86400000).toISOString().slice(0, 10);
const denied = (fn, code = '42501') => assert.rejects(fn, e => e.code === code);

async function runSuite({withTrgm, withExtensionsSchema = false}) {
  const db = withTrgm ? new PGlite({extensions: {pg_trgm}}) : new PGlite();
  try {
    await db.exec(`
      ${withExtensionsSchema ? 'create schema if not exists extensions;' : ''}
      create role anon noinherit;
      create role authenticated noinherit;
      create schema auth;
      create table auth.users(id uuid primary key);
      create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
      grant usage on schema auth to anon,authenticated;
      grant execute on function auth.uid() to anon,authenticated;
    `);

    // Apply 001–003 before seeding legacy records, then 004–007.
    for (const file of MIGRATIONS.slice(0, 3)) await db.exec(sqlByFile[file]);
    for (let n = 1; n <= 35; n++) await db.query('insert into auth.users values ($1)', [uid(n)]);

    const person = async (n, name, isPublic = true, display = 'Deniz', ids = [603], ratings = false) => {
      if (name) await db.query('insert into mml_private.usernames(user_id,username) values ($1,$2)', [uid(n), name]);
      await db.query(
        'insert into mml_private.profiles(user_id,is_public,display_name,tmdb_ids,show_ratings) values ($1,$2,$3,$4,$5)',
        [uid(n), isPublic, display, ids, ratings],
      );
    };

    await person(1, 'deniz', true, 'Deniz', [603, 550, 13, 22, 30, 55], true);
    await person(2, 'burcu', false, 'PRIVATE-100%_\\DISPLAY');
    await person(3, 'mert', true, 'Deniz', [603, 550], false);
    await person(4, 'hitler', true, 'Safe display'); // legacy disallowed handle; suppressed
    await person(5, 'safe_handle', true, 'H1TL3R'); // legacy disallowed display name; suppressed
    await person(6, null, true, 'No handle');
    // Literal wildcard / escape test identities:
    await person(7, 'pct_fan', true, '100% Cinema', [603], true);
    await person(8, 'under_score', true, 'Under_Score', [603], false);
    await person(9, 'slash_fan', true, 'Back\\Slash', [603], false);
    await person(10, 'combo_fan', true, 'Mix_%\\Quote\'End', [603], true);
    await person(11, 'plainuser', true, 'Plain Viewer', [603], false);
    for (let n = 12; n <= 35; n++) {
      await person(n, 'reader' + String(n).padStart(3, '0'), true, 'Film lover ' + n, [603, 550], n % 2 === 0);
    }

    for (const file of MIGRATIONS.slice(3, 7)) await db.exec(sqlByFile[file]);

    const dates = (await db.query(
      "select (now() at time zone 'UTC')::date::text today, ((now() at time zone 'UTC')::date-(extract(isodow from (now() at time zone 'UTC')::date)::int-1))::text first",
    )).rows[0];
    const earlierInWeek = dates.today > dates.first ? shift(dates.today, -1) : dates.first;

    const recordData = (n, extra = {}) => ({
      status: 'Watched',
      rating: 9,
      note: 'SECRET-NOTE-' + n,
      favorite: true,
      watched_date: dates.today,
      added_at: '2024-01-01T00:00:00.000000+00:00',
      order_key: `00000000000000000001:${uid(n)}`,
      deleted_at: null,
      custom: null,
      ...extra,
    });
    const film = async (n, mid, extra = {}) => {
      const rev = (await db.query('select coalesce(max(revision),0)+1 rev from public.mml_library where user_id=$1', [uid(n)])).rows[0].rev;
      await db.query(
        'insert into public.mml_library(user_id,record_key,data,revision) values ($1,$2,$3,$4)',
        [uid(n), 'tmdb:' + mid, JSON.stringify(recordData(n, extra)), rev],
      );
    };

    // User 1: 603 watched today, 550 watchlist (excluded), 13 null date (excluded),
    // 22 prior week (excluded), 30 deleted (excluded), 55 next week (excluded), 999 unshowcased (excluded).
    await film(1, 603, {watched_date: dates.today, rating: 9});
    await film(1, 550, {status: 'Watchlist'});
    await film(1, 13, {watched_date: null});
    await film(1, 22, {watched_date: shift(dates.first, -1)});
    await film(1, 30, {deleted_at: '2026-10-01T00:00:00+00:00'});
    await film(1, 55, {watched_date: shift(dates.first, 7)});
    await film(1, 999, {watched_date: dates.today});

    // User 3: two films watched on different days (when today > Monday) + same-day tiebreak by tmdb_id.
    await film(3, 603, {watched_date: dates.today, rating: 8});
    await film(3, 550, {watched_date: earlierInWeek, rating: 7});

    for (let n = 2; n <= 35; n++) {
      if (n === 3) continue;
      await film(n, 603, {watched_date: n % 3 === 0 ? earlierInWeek : dates.today, rating: 8});
      if (n >= 12 && n <= 16) await film(n, 550, {watched_date: dates.today, rating: 10});
    }

    const page = async (view = 'people', query = '', cursor = null) =>
      (await db.query('select public.mml_social_page($1,$2,$3) value', [view, query, cursor === null ? null : JSON.stringify(cursor)])).rows[0].value;

    const collectAll = async (view, query = '') => {
      let cur = null;
      const rows = [];
      for (;;) {
        const res = await page(view, query, cur);
        rows.push(...res.rows);
        if (!res.next_cursor) return rows;
        cur = res.next_cursor;
      }
    };

    // Snapshot exact 005 baseline outputs across all literal/wildcard/SQLi queries and full paginated views.
    const testQueries = [
      '',
      '  ',
      'DENIZ',
      'deniz',
      'reader',
      '%',
      '100%',
      '_',
      'under_score',
      '\\',
      'back\\',
      'back\\slash',
      '_%\\',
      "quote'end",
      "' OR 1=1 --",
      "'; DROP TABLE public.mml_library; --",
      '%" OR 1=1 --',
      'PRIVATE',
      'missing',
    ];
    await db.exec('set role anon');
    const baselinePeople = {};
    const baselineWeek = {};
    for (const q of testQueries) {
      baselinePeople[q] = await collectAll('people', q);
      baselineWeek[q] = await collectAll('week', q);
    }
    await db.exec('reset role');

    // Apply migration 008.
    await db.exec(sqlByFile['008_social_scale_indexes.sql']);

    // Verify expected indexes exist in pg_indexes.
    const indexRows = (await db.query(`
      select schemaname, tablename, indexname, indexdef
      from pg_indexes
      where schemaname in ('public', 'mml_private')
    `)).rows;
    const byName = Object.fromEntries(indexRows.map(r => [r.indexname, r]));

    assert.ok(byName.mml_library_active_watched_date, 'global partial watched_date index must exist');
    assert.equal(byName.mml_library_active_watched_date.schemaname, 'public');
    assert.equal(byName.mml_library_active_watched_date.tablename, 'mml_library');
    assert.match(byName.mml_library_active_watched_date.indexdef, /watched_date.*DESC/i);
    assert.match(byName.mml_library_active_watched_date.indexdef, /WHERE/i);

    assert.ok(byName.mml_library_user_active_watched_date, 'per-user partial watched_date index must exist');
    assert.equal(byName.mml_library_user_active_watched_date.schemaname, 'public');
    assert.equal(byName.mml_library_user_active_watched_date.tablename, 'mml_library');
    assert.match(byName.mml_library_user_active_watched_date.indexdef, /user_id.*watched_date.*DESC/i);
    assert.match(byName.mml_library_user_active_watched_date.indexdef, /WHERE/i);

    assert.ok(byName.mml_usernames_username_c, 'C-collation username index must exist');

    if (withTrgm) {
      const ext = (await db.query(`
        select e.extname, n.nspname
        from pg_extension e join pg_namespace n on n.oid = e.extnamespace
        where e.extname = 'pg_trgm'
      `)).rows;
      assert.equal(ext.length, 1, 'pg_trgm extension must be installed');
      if (withExtensionsSchema) assert.equal(ext[0].nspname, 'extensions');

      assert.ok(byName.mml_usernames_username_trgm, 'GIN trigram index on usernames must exist');
      assert.match(byName.mml_usernames_username_trgm.indexdef, /USING gin/i);
      assert.match(byName.mml_usernames_username_trgm.indexdef, /gin_trgm_ops/i);

      assert.ok(byName.mml_profiles_display_name_trgm, 'partial GIN trigram index on public display_name must exist');
      assert.match(byName.mml_profiles_display_name_trgm.indexdef, /USING gin/i);
      assert.match(byName.mml_profiles_display_name_trgm.indexdef, /gin_trgm_ops/i);
      assert.match(byName.mml_profiles_display_name_trgm.indexdef, /WHERE is_public/i);
    } else {
      assert.ok(byName.mml_usernames_username_pattern, 'fallback text_pattern_ops index on usernames must exist');
      assert.match(byName.mml_usernames_username_pattern.indexdef, /text_pattern_ops/i);

      assert.ok(byName.mml_profiles_display_name_pattern, 'fallback text_pattern_ops index on public display_name must exist');
      assert.match(byName.mml_profiles_display_name_pattern.indexdef, /text_pattern_ops/i);
      assert.match(byName.mml_profiles_display_name_pattern.indexdef, /WHERE is_public/i);
    }

    // Verify function security attributes and grants remain exact.
    const fnMeta = (await db.query(`
      select p.prosecdef, p.proconfig,
             has_function_privilege('anon', p.oid, 'EXECUTE') as anon_exec,
             has_function_privilege('authenticated', p.oid, 'EXECUTE') as auth_exec,
             has_function_privilege('public', p.oid, 'EXECUTE') as pub_exec
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public' and p.proname = 'mml_social_page'
    `)).rows[0];
    assert.equal(fnMeta.prosecdef, true);
    assert.deepEqual(fnMeta.proconfig, ['search_path=""']);
    assert.equal(fnMeta.anon_exec, true);
    assert.equal(fnMeta.auth_exec, true);
    assert.equal(fnMeta.pub_exec, false);

    // Compare 008 outputs against 005 baseline for every single query (100% identical semantics).
    await db.exec('set role anon');
    for (const q of testQueries) {
      assert.deepEqual(await collectAll('people', q), baselinePeople[q], `people mismatch for query ${JSON.stringify(q)}`);
      assert.deepEqual(await collectAll('week', q), baselineWeek[q], `week mismatch for query ${JSON.stringify(q)}`);
    }

    // Explicit literal substring assertions for %, _, \, quotes, case-insensitivity, and SQLi.
    assert.deepEqual((await page('people', '%')).rows.map(r => r.username), ['combo_fan', 'pct_fan']);
    assert.deepEqual((await page('people', '100%')).rows.map(r => r.username), ['pct_fan']);
    assert.deepEqual((await page('people', '_')).rows.map(r => r.username), ['combo_fan', 'pct_fan', 'slash_fan', 'under_score']);
    assert.deepEqual((await page('people', 'UNDER_SCORE')).rows.map(r => r.username), ['under_score']);
    assert.deepEqual((await page('people', '\\')).rows.map(r => r.username), ['combo_fan', 'slash_fan']);
    assert.deepEqual((await page('people', 'back\\')).rows.map(r => r.username), ['slash_fan']);
    assert.deepEqual((await page('people', '_%\\')).rows.map(r => r.username), ['combo_fan']);
    assert.deepEqual((await page('people', "QUOTE'END")).rows.map(r => r.username), ['combo_fan']);
    assert.deepEqual((await page('week', '%')).rows.map(r => r.username), ['combo_fan', 'pct_fan']);
    assert.deepEqual((await page('week', '\\')).rows.map(r => r.username), ['combo_fan', 'slash_fan']);
    assert.deepEqual((await page('people', "' OR 1=1 --")).rows, []);
    assert.deepEqual((await page('week', "'; DROP TABLE public.mml_library; --")).rows, []);
    assert.deepEqual((await page('people', 'PRIVATE')).rows, []);

    // Verify This week ordering, pagination boundaries, and stale-week rollover.
    const allWeek = await collectAll('week', '');
    assert.equal(allWeek.length, 37); // 31 public allowed users with 603 + 6 extra 550 watches (user 3 + users 12..16)
    for (let i = 1; i < allWeek.length; i++) {
      const a = allWeek[i - 1], b = allWeek[i];
      const ordered =
        a.watched_date > b.watched_date ||
        (a.watched_date === b.watched_date && a.username < b.username) ||
        (a.watched_date === b.watched_date && a.username === b.username && a.tmdb_id < b.tmdb_id);
      assert.ok(ordered, `week ordering violated at index ${i}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
    }
    assert.ok(!JSON.stringify(allWeek).includes('SECRET') && !JSON.stringify(allWeek).includes('PRIVATE'));
    assert.deepEqual(allWeek.filter(e => e.username === 'deniz'), [
      {username: 'deniz', display_name: 'Deniz', avatar_id: 'cat-luna', tmdb_id: 603, watched_date: dates.today, rating: 9},
    ]);
    assert.ok(!('rating' in allWeek.find(e => e.username === 'mert')));

    const firstWeekPage = await page('week', '');
    assert.equal(firstWeekPage.rows.length, 12);
    assert.ok(firstWeekPage.next_cursor);
    const staleCursor = {
      ...firstWeekPage.next_cursor,
      watched_date: shift(dates.first, -1),
      week_start: shift(dates.first, -7),
    };
    assert.deepEqual(await page('week', '', staleCursor), firstWeekPage);

    // Verify search-filtered multi-page keyset pagination (people & week) and invalid input rejection.
    const readerPeoplePage1 = await page('people', 'reader');
    assert.equal(readerPeoplePage1.rows.length, 16);
    assert.ok(readerPeoplePage1.next_cursor);
    const readerPeoplePage2 = await page('people', 'reader', readerPeoplePage1.next_cursor);
    assert.equal(readerPeoplePage2.rows.length, 8);
    assert.equal(readerPeoplePage2.next_cursor, null);
    assert.equal(new Set([...readerPeoplePage1.rows, ...readerPeoplePage2.rows].map(r => r.username)).size, 24);

    const readerWeekPage1 = await page('week', 'reader');
    assert.equal(readerWeekPage1.rows.length, 12);
    assert.ok(readerWeekPage1.next_cursor);
    const allReaderWeek = await collectAll('week', 'reader');
    assert.equal(allReaderWeek.length, 29);
    assert.equal(new Set(allReaderWeek.map(e => `${e.username}:${e.tmdb_id}`)).size, 29);

    for (const [v, q, c] of [
      ['wrong', '', null],
      ['people', 'x'.repeat(61), null],
      ['people', 'bad\nname', null],
      ['people', '', {}],
      ['people', '', {username: 'deniz', user_id: uid(2)}],
      ['week', '', {username: 'deniz'}],
      ['week', '', {username: 'deniz', watched_date: '2026-99-00', tmdb_id: 603, week_start: dates.first}],
    ]) {
      await denied(() => page(v, q, c), '22023');
    }

    // Verify RLS denials for anon.
    await denied(() => db.query('select * from public.mml_library'));
    await denied(() => db.query('select * from mml_private.profiles'));
    await denied(() => db.query('select * from mml_private.usernames'));
    await denied(() => db.query("select mml_private.name_allowed('deniz')"));

    // Verify authenticated RLS isolation + immediate privacy revocation.
    await db.exec('reset role');
    const countBefore = (await db.query('select count(*)::int n from public.mml_library')).rows[0].n;
    await db.query("select set_config('request.jwt.claim.sub',$1,false)", [uid(1)]);
    await db.exec('set role authenticated');
    const ownRows = (await db.query('select distinct user_id from public.mml_library')).rows;
    assert.deepEqual(ownRows, [{user_id: uid(1)}]);
    await denied(() => db.query('delete from public.mml_library'));
    await denied(() => db.query('select * from mml_private.profiles'));
    await db.query("select public.mml_write_showcase($1,0,'unpublish','{}')", [uid(900)]);

    await db.exec('set role anon');
    assert.deepEqual((await page('people', 'deniz')).rows.map(r => r.username), ['mert']);
    assert.deepEqual((await page('week', 'deniz')).rows.map(r => r.username), ['mert', 'mert']);

    // Verify safe replay of 008 (and full 001–008 replay) keeps rows, privacy state, indexes, and RLS intact.
    await db.exec('reset role');
    await db.exec(sqlByFile['008_social_scale_indexes.sql']);
    for (const file of MIGRATIONS) await db.exec(sqlByFile[file]);

    assert.equal((await db.query('select count(*)::int n from public.mml_library')).rows[0].n, countBefore);
    assert.equal((await db.query('select is_public from mml_private.profiles where user_id=$1', [uid(1)])).rows[0].is_public, false);
    await db.exec('set role anon');
    await denied(() => db.query('select * from public.mml_library'));
    assert.deepEqual((await page('people', 'deniz')).rows.map(r => r.username), ['mert']);
  } finally {
    await db.close();
  }
}

await runSuite({withTrgm: true, withExtensionsSchema: false});
await runSuite({withTrgm: true, withExtensionsSchema: true});
await runSuite({withTrgm: false, withExtensionsSchema: false});

console.log('PASS: Social scale indexes (008) — 001–008 apply/replay; pg_trgm GIN (default & extensions schema) + B-tree fallback; partial watched_date indexes; exact literal LIKE escaping (%, _, \\, quotes, SQLi); identical 005/008 semantics; week ordering/pagination/rollover; privacy revocation and RLS intact.');
