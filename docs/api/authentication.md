# Authentication and tenant selection

## Tokens

| Token | Lifetime (default) | Use |
|---|---|---|
| Access (JWT, HS256) | 15 min (`ACCESS_TOKEN_TTL_MINUTES`) | `Authorization: Bearer <token>` on every request |
| Refresh (JWT, HS256) | 14 days (`REFRESH_TOKEN_TTL_DAYS`) | `POST /auth/refresh` only |

Both tokens carry `sub` (user id), `typ` (`access` or `refresh`), `jti`, `iat`,
`exp`, `iss` and `aud`. The server accepts only HS256 with its own secret, so
`alg: none` and algorithm-confusion tokens are rejected. A refresh token
cannot be used as an access token, and an access token cannot be used to
refresh.

### Refresh rotation and reuse detection

Each login starts a **token family**. Every `POST /auth/refresh` revokes the
token it receives and returns a new pair in the same family. If a revoked
token is presented again, someone may hold a copy of it, so the server
revokes the whole family and the user must log in again. Other logins (other
devices) are not affected.

Clients must therefore never refresh the same token twice in parallel.
Mobile clients serialize refreshes behind a single in-flight request.

`POST /auth/logout` revokes the family of the given refresh token. It answers
`204` even for unknown tokens, so it never reveals whether a token was valid.

### Passwords

Passwords are hashed with Argon2id (argon2-cffi defaults, RFC 9106 low-memory
profile). Hashes are upgraded transparently at login when the parameters
change. When the email does not exist, login still verifies against a dummy
hash, so response timing does not reveal registered emails. Wrong password,
unknown email and inactive account all return the same `401` message.

Failed logins are throttled per account and per client address (Redis, Week 6):
`429` with `Retry-After`. Not yet implemented: password reset and invitations.

## Choosing the institution

Tenant-scoped endpoints (`/campuses` and everything that follows) resolve the
institution this way:

1. `X-Institution-Id: <uuid>` header, if present. It is used only when the
   user has an **active** membership in that institution. Otherwise the
   answer is `403`, the same whether the institution exists or not.
2. Without the header, the user's only active membership. Users with several
   memberships get `400` and must send the header.

The resolved institution is then set as `app.current_institution_id` for the
request transaction, and PostgreSQL RLS restricts every query to it. Request
bodies never carry `institution_id` (schemas use `extra="forbid"`).

## Endpoints (Week 2)

| Method | Path | Who |
|---|---|---|
| POST | `/api/v1/auth/login` | anyone |
| POST | `/api/v1/auth/refresh` | holder of a refresh token |
| POST | `/api/v1/auth/logout` | holder of a refresh token |
| GET | `/api/v1/users/me` | authenticated |
| GET | `/api/v1/institutions` | authenticated (own institutions only) |
| POST | `/api/v1/institutions` | Super Admin (platform connection) |
| GET | `/api/v1/campuses` | any active member |
| POST | `/api/v1/campuses` | School Admin |
| POST | `/api/v1/geofences` | School Admin (Week 3) |
| GET | `/api/v1/geofences` | any active member (Week 3) |
| POST | `/api/v1/geofences/check` | any active member, dry run (Week 3) |
| POST/GET | `/api/v1/students` | School Admin (create); admin or teacher (list) |
| POST/GET | `/api/v1/staff` | School Admin |
| POST/GET | `/api/v1/devices` | authenticated (own devices) |
| POST | `/api/v1/attendance/events` | the student or staff member themselves |
| GET | `/api/v1/attendance/events` | own events; School Admin sees all |
| GET | `/api/v1/attendance/state` | the student or staff member themselves |
| POST | `/api/v1/attendance/manual-events` | School Admin (audited) |
| POST | `/api/v1/attendance/events/{id}/review` | School Admin (audited) |
| POST | `/api/v1/attendance/events/sync` | the student or staff member (offline batch) |
| GET | `/api/v1/attendance/guardian/students` | guardians |
| POST/GET | `/api/v1/guardians`, POST `/api/v1/guardians/{id}/students` | School Admin (linking audited) |
| GET | `/api/v1/notifications`, POST `/api/v1/notifications/{id}/read` | authenticated (own) |
| POST | `/api/v1/accounts` | School Admin (audited) |
| POST | `/api/v1/users/me/password` | authenticated (signs out every session) |
| PATCH | `/api/v1/students/{id}` | School Admin (link/unlink account, rename, activate; audited) |
| GET | `/api/v1/analytics/attendance` (+ `.csv`) | School Admin, Teacher |
| PATCH/DELETE | `/api/v1/geofences/{id}` | School Admin (delete only if never used; audited) |
| GET | `/api/v1/platform/institutions`, POST `/api/v1/platform/institutions/{id}/admins` | Super Admin |

## Bootstrapping the first Super Admin

```bash
docker compose exec api python -m app.cli create-platform-admin \
    --email admin@example.test --name "Platform Admin"
```

The command prompts for the password, or reads it from
`SCHOOLTRACK_ADMIN_PASSWORD`. It runs with the owner connection, because no
API path can create platform administrators.
