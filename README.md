# iyoroynet-autopeer

Python/FastAPI control-plane API for DN42 autopeering backed by the existing
`Bird2-Configuration` Ansible repository.

## Scope of this MVP

- ASN is the login identity and ownership key.
- Normal users may only create/update/delete `ansible/host_vars/<node>/dn42-peers/<asn>.yml`
  for their own ASN.
- User-editable peer fields are intentionally narrow: contact information (stored as the
  generated BIRD description), one WireGuard public key, one endpoint, link MTU, BGP transport
  address, address-family request, and extended-next-hop.
- WireGuard preshared keys are deliberately out of scope for this MVP until their lifecycle,
  encryption, and rotation policy are designed.
- The backend writes canonical YAML, updates git, runs Ansible render/validate, and optionally
  deploys through the playbooks stored in the Bird2-Configuration repo.
- Metrics are fetched periodically by a bounded background collector, kept in process memory, and
  parsed from exporter `/metrics` endpoints with `prometheus-client`; Prometheus is not required for
  the MVP.

## Current important limitations

The current `Bird2-Configuration` layout stores peer files under `host_vars/<node>/dn42-peers/`.
Ansible recursively loads host var subdirectories, so these peer YAML files also leak keys like
`asn`, `wireguard`, `lla`, and `bgp` into the host variable namespace. The existing render works
because `ansible/tasks/load-dn42-peers.yml` aggregates them into `dn42.peers`, but this is a known
configuration limitation. The backend therefore never reads host state through `ansible-inventory`;
it parses the YAML files directly and only writes the fixed `dn42-peers/<asn>.yml` path.

The targeted peer playbook lives in
`Bird2-Configuration/ansible/playbooks/deploy-dn42-peer.yml`. It renders only
`dn42_<asn>.conf` and `dn42/peers/dn42_<asn>.conf` for the selected peer, then
updates only those remote files, runs `birdc configure`, and starts/stops or
syncs only that WireGuard interface. It deliberately does not run the host-wide
render or validate playbooks.

## Repository layout

```text
src/autopeer/
  api/            FastAPI routers and dependencies
  adapters/       Git, Ansible, config-repo and metrics adapters
  core/           settings, logging and auth helpers
  domain/         Pydantic domain models and validators
  services/       peer, job, worker and metrics orchestration
  db/             SQLite job store
frontend/         Vue 3 + Vite + mdui peer/admin UI
tests/            unit/integration tests
```

## Frontend

The repository includes a Vue 3 + Vite frontend using [mdui](https://www.mdui.org/) web components
under `frontend/`. It supports Kioubit login, development-header login, node/peer selection, peer
create/edit/delete jobs, job polling, and exporter-derived session status cards. mdui works directly
with Vue because its components are standard web components.

Run both services with Docker Compose:

```bash
docker compose up --build
```

The backend image can also run independently after mounting a writable config repository and data directory:

```bash
docker build -t iyoroynet-autopeer .
docker run --rm -p 8080:8080 \
  -v /path/to/Bird2-Configuration:/config-repo \
  -v autopeer-data:/data/autopeer \
  --env-file .env \
  iyoroynet-autopeer
```

GitHub Actions runs backend checks, frontend builds, and a Docker build for pull requests. Pushes to
`main` and `v*` tags also publish the backend image to `ghcr.io/<owner>/<repository>`.

Open the frontend at `http://127.0.0.1:5173`. Vite proxies `/api/*` to the API service, so browser
requests retain the signed Kioubit session cookie without CORS configuration. For local frontend-only
development, run `npm install && npm run dev` from `frontend/`; its default proxy target is
`http://localhost:8080`.

## Development

Recommended local setup with `uv`:

```bash
uv venv
uv pip install -e '.[dev]'
cp .env.example .env
uvicorn autopeer.main:app --reload --host 0.0.0.0 --port 8080
```

Without `uv`:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn autopeer.main:app --reload
```

In a second terminal for the frontend:

```bash
cd frontend
npm install
npm run dev
```

Development auth uses headers. In production the Vue frontend uses Kioubit's documented
`<kioubit-auth-btn>` form component. It submits `return=https://<frontend-origin>/api/v1/auth/callback`
to Kioubit; the frontend proxy forwards the signed callback to the backend, which verifies
signature/domain/freshness and stores the returned identity in the local session:

```bash
curl -H 'X-Autopeer-ASN: 4242423128' http://127.0.0.1:8080/api/v1/me
```

## Key environment variables

All settings use the `AUTOPEER__` prefix and `__` nested delimiter.

| Variable | Default | Meaning |
|---|---:|---|
| `AUTOPEER__CONFIG_REPO_PATH` | `/config-repo` | Dedicated Bird2-Configuration checkout |
| `AUTOPEER__DATABASE_PATH` | `/data/autopeer/jobs.sqlite3` | SQLite job store |
| `AUTOPEER__DEPLOY_ENABLED` | `false` | Actually run production deploy playbooks |
| `AUTOPEER__GIT_PUSH_ENABLED` | `false` | Push commits after successful validation |
| `AUTOPEER__GIT_SYNC_ENABLED` | `false` | Run `git pull --ff-only` before a mutation job |
| `AUTOPEER__ALLOW_DIRTY_REPO` | `false` | Permit committing in a dirty config checkout |
| `AUTOPEER__GIT_AUTHOR_NAME` | `Autopeer Bot` | Commit author name for automated changes |
| `AUTOPEER__GIT_AUTHOR_EMAIL` | `autopeer@localhost` | Commit author email for automated changes |
| `AUTOPEER__AUTH_MODE` | `dev-header` | `dev-header` locally, `kioubit` in production |
| `AUTOPEER__SESSION_SECRET` | unset | Required session-signing secret in Kioubit mode |
| `AUTOPEER__KIOUBIT_DOMAIN` | unset | Domain expected in Kioubit's signed response |
| `AUTOPEER__KIOUBIT_PUBLIC_KEY_FILE` | unset | PEM public key used to verify Kioubit signatures |
| `AUTOPEER__ADMIN_ASNS` | empty | Comma-separated admin ASN allowlist, for example `4242422024,4242423128` |
| `AUTOPEER__METRICS_TARGETS_FILE` | unset | YAML map of exporter URLs |

`config/kioubit-public-key.pem` contains the Kioubit public verification key from their example.
It is public material, not a private credential. Configure `AUTOPEER__KIOUBIT_DOMAIN` with the
public host name registered with Kioubit (without a path); it must match the signed `domain` value.
The verified `asn` remains the only authorization identity. A bounded `effective_name` is retained
as the non-authoritative `display_name` shown by `/api/v1/me`; fields such as prefixes, contacts,
maintainer data, and tokens from Kioubit's response are discarded.

Example metrics target file:

```yaml
nodes:
  hkg02-hk:
    wireguard: http://hkg02.example:9586/metrics
    bird: http://hkg02.example:9324/metrics
    node: http://hkg02.example:9100/metrics
```

## API sketch

- `GET /healthz` process health
- `GET /readyz` dependency readiness
- `GET /api/v1/auth/callback` verify Kioubit `params` and `signature`, then create a session
- `POST /api/v1/auth/logout` clear the current session
- `GET /api/v1/me` current principal
- `GET /api/v1/nodes` peering-enabled nodes
- `GET /api/v1/nodes/{node}/peers` current user's peers on a node
- `POST /api/v1/nodes/{node}/peers` create current ASN peer
- `GET/PATCH/DELETE /api/v1/nodes/{node}/peers/{asn}` read/update/delete peer
- `GET /api/v1/jobs/{job_id}` job status
- `GET /api/v1/me/peers/status` exporter-derived peer status for current ASN

Mutating endpoints enqueue jobs; they do not run Ansible in the HTTP request path.
