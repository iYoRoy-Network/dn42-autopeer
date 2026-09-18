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

The current deployment flow can either use the legacy targeted peer playbook or the new agent-backed flow. The Go agent reads the node-local WireGuard private key and local BGP addresses from its own environment. `AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY` is the base64 private-key value itself; it is never sent in the deployment request:

```text
AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY=<base64-private-key>
AUTOPEER_AGENT_OWN_V4=172.20.234.225
AUTOPEER_AGENT_OWN_V6=fd18:3e15:61d0::1
```

Those values are never sent in the deployment request. The backend request only contains the remote peer data and session mode.

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

The repository includes a Vue 3 + TypeScript frontend under `frontend/`, built with
[Ant Design Vue](https://antdv.com/), `vue-i18n` (English + Simplified Chinese), `vue-router`, and
`dayjs`. It supports DN42 OIDC login (plus development-header login in dev builds), node browsing,
per-node session tables with view/edit/delete actions, a three-step peer wizard, and job polling.
The layout and visual style are inspired by the iEdon-Net Auto Peering frontend (see
[acknowledgments](#acknowledgments)).

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

GitHub Actions runs backend checks, frontend builds, and Go agent tests for pull requests. Pushes to `main`
and `v*` tags also publish two GHCR images:

```text
ghcr.io/<owner>/<repository>-backend
ghcr.io/<owner>/<repository>-frontend
```

The frontend image only serves the compiled static files. Route `/api/*`, `/healthz`, and `/readyz`
through your own reverse proxy to the backend service. For local frontend-only development, run
`npm install && npm run dev` from `frontend/`; its Vite proxy target defaults to
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

Development auth uses headers. Production uses the DN42 OpenID Connect provider at
`https://dn42.g-load.eu` with Authorization Code + PKCE. Register the exact public callback URL
with the OAuth application, for example:

```text
https://autopeer.example.dn42/api/v1/auth/callback
```

The frontend only links to `/api/v1/auth/login`; the backend performs discovery, code exchange,
ID-token validation, and extracts the ASN from the provider's `dn42` claim. Client credentials and
tokens never reach the browser. The reverse proxy must forward `/api/v1/auth/*` to the backend.

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
| `AUTOPEER__AUTH_MODE` | `dev-header` | `dev-header` locally, `oidc` in production |
| `AUTOPEER__SESSION_SECRET` | unset | Required session-signing secret in OIDC mode |
| `AUTOPEER__OIDC_ISSUER` | `https://dn42.g-load.eu` | OIDC provider issuer |
| `AUTOPEER__OIDC_CLIENT_ID` | unset | OAuth application client ID |
| `AUTOPEER__OIDC_CLIENT_SECRET` | unset | OAuth client secret, preferably supplied through a secret file |
| `AUTOPEER__OIDC_CLIENT_SECRET_FILE` | unset | File containing the OAuth client secret |
| `AUTOPEER__OIDC_REDIRECT_URI` | unset | Exact callback URL registered with the provider |
| `AUTOPEER__ADMIN_ASNS` | empty | Comma-separated admin ASN allowlist, for example `4242422024,4242423128` |
| `AUTOPEER__METRICS_TARGETS_FILE` | unset | YAML map of exporter URLs |
| `AUTOPEER__AGENT_ENABLED` | `false` | Send peer deployments to node agents instead of targeted Ansible |
| `AUTOPEER__AGENT_CA_FILE` | unset | CA bundle used to verify node-agent certificates |
| `AUTOPEER__AGENT_CLIENT_CERT_FILE` | unset | Backend mTLS client certificate |
| `AUTOPEER__AGENT_CLIENT_KEY_FILE` | unset | Backend mTLS client private key |
| `AUTOPEER__AGENT_SIGNING_PRIVATE_KEY_FILE` | unset | Ed25519 key used for request signatures |
| `AUTOPEER__AGENT_TIMEOUT_SECONDS` | `15` | Agent request timeout |

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

## Acknowledgments

The frontend's layout, page structure, and visual style are inspired by the
[iEdon-Net Auto Peering](https://iedon.net) frontend (GitHub: `iedon-net/iedon-net-frontend`),
which is licensed under [GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html). We thank the iEdon-Net
maintainers for making their work public. This project's frontend code is a fresh implementation for
the iyoroynet-autopeer API; attribution is included in the site footer and in
`frontend/src/config.ts`.

> **Note on licensing:** this repository does not currently declare a license. If the frontend is
> distributed as a derivative of the GPL-3.0 iEdon-Net frontend, the combined work must be licensed
> under GPL-3.0-compatible terms. Please confirm the intended license before publishing.
