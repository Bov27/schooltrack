# Week 5: Clients

Week 5 ships in two pull requests: the admin dashboard (5a) and the mobile app (5b).

## 5a: Admin dashboard (`apps/web`, Next.js)

### Delivered

- [x] **Backend-for-frontend (BFF) authentication.** The browser never sees a
      token. Login goes through `/api/auth/login`, which stores the access and
      refresh tokens in `httpOnly`, `SameSite=Strict` cookies. Every API call
      goes through `/api/backend/<path>`, which attaches the token, refreshes
      it once on `401` and clears the session when refreshing fails.
- [x] **The proxy is restrictive.** It accepts only paths under `/api/v1`
      (no traversal) and forwards an allow-list of request headers (the
      browser's own `Authorization` and `Cookie` headers are dropped).
- [x] Pages:
  - overview;
  - attendance: review queue, filters, coordinates shown to admins only,
    manual entries;
  - campuses and geofences: centre + radius or GeoJSON, plus "test a point",
    which stores nothing;
  - students and staff;
  - institutions (platform admins).
- [x] Institution switcher for users who belong to several institutions. It
      sets the `X-Institution-Id` hint, which the API validates.
- [x] Security headers (`X-Frame-Options: DENY`, `nosniff`,
      `Referrer-Policy`, `Permissions-Policy`); safe post-login redirects
      (same-site relative paths only).
- [x] Unit tests (vitest) for the refresh/retry logic, path sanitising,
      header filtering and formatting helpers.
- [x] CI (`web-ci`): type check, unit tests, production build. Docker image
      (standalone output, non-root) and a `web` service in Compose.

### Decisions

- **No UI framework or data-fetching library.** The dashboard's needs are
  modest, and every dependency is something to audit and update. A small
  `useApi` hook covers loading, error and reload.
- **No map yet.** Geofences are created from coordinates or GeoJSON, and
  "test a point" gives immediate feedback. A map editor (Leaflet) is a later
  improvement that will not change the API.
- **Lockfile:** the authoring environment had no access to the npm registry,
  so the first CI run resolved the dependency tree. Its `package-lock.json`
  was then committed (Next 15.5.29, React 19.3.1), and CI and Docker now
  install with `npm ci`.
