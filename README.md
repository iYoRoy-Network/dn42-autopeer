# iyoroynet-autopeer

Python/FastAPI control-plane API for DN42 autopeering backed by the existing
`Bird2-Configuration` Ansible repository.

## Scope of this MVP

- ASN is the login identity and ownership key.
- Normal users may only create/update/delete `ansible/host_vars/<node>/dn42-peers/<asn>.yml`
  for their own ASN.
- User-editable peer fields are intentionally narrow: description, one WireGuard public key,
  one endpoint, BGP transport address, address-family request, and extended-next-hop.
- WireGuard preshared keys are deliberately out of scope for this MVP until their lifecycle,
  encryption, and rotation policy are designed.
- The backend writes canonical YAML, updates git, runs Ansible render/validate, and optionally
  deploys.
- Metrics are fetched directly from exporter `/metrics` endpoints and parsed with
  `prometheus-client`; Prometheus is not required for the MVP.

## Current important limitations

The current `Bird2-Configuration` layout stores peer files under `host_vars/<node>/dn42-peers/`.
Ansible recursively loads host var subdirectories, so these peer YAML files also leak keys like
`asn`, `wireguard`, `lla`, and `bgp` into the host variable namespace. The existing render works
because `ansible/tasks/load-dn42-peers.yml` aggregates them into `dn42.peers`, but this is a known
configuration limitation. The backend therefore never reads host state through `ansible-inventory`;
it parses the YAML files directly and only writes the fixed `dn42-peers/<asn>.yml` path.

Existing Ansible playbooks can deploy at host granularity, not ASN granularity. This project also
ships an optional targeted peer playbook under `ansible/playbooks/deploy-dn42-peer.yml`, but the
safest default remains host-level full render/validate before any remote apply.

## Repository layout

```text
src/autopeer/
  api/            FastAPI routers and dependencies
  adapters/       Git, Ansible, config-repo and metrics adapters
  core/           settings, logging and auth helpers
  domain/         Pydantic domain models and validators
  services/       peer, job, worker and metrics orchestration
  db/             SQLite job store
ansible/          autopeer-specific targeted playbooks
tests/            unit/integration tests
```

## Frontend repo recommendation

Start with a monorepo: keep a future Vue/Vite frontend in `frontend/` in this repository. The API
contract, Docker Compose, dev auth, and deployment dashboard will evolve together early on. Split
frontend into a separate repository later only if release cadence, permissions, or hosting diverge.

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

Development auth uses headers. Production uses Kioubit OIDC once its discovery URL and
ASN claim name are configured:

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
| `AUTOPEER__OIDC_*` | unset | Kioubit OIDC discovery, client and ASN claim configuration |
| `AUTOPEER__ADMIN_ASNS` | empty | Comma-separated admin ASN list |
| `AUTOPEER__METRICS_TARGETS_FILE` | unset | YAML map of exporter URLs |

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
- `GET /api/v1/me` current principal
- `GET /api/v1/nodes` peering-enabled nodes
- `GET /api/v1/nodes/{node}/peers` current user's peers on a node
- `POST /api/v1/nodes/{node}/peers` create current ASN peer
- `GET/PATCH/DELETE /api/v1/nodes/{node}/peers/{asn}` read/update/delete peer
- `GET /api/v1/jobs/{job_id}` job status
- `GET /api/v1/me/peers/status` exporter-derived peer status for current ASN

Mutating endpoints enqueue jobs; they do not run Ansible in the HTTP request path.
