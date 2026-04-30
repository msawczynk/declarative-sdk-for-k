# Commander Service Mode

`CommanderServiceProvider` talks to Keeper Commander Service Mode REST API v2.
It is a transport alternative to the CLI provider: same capability gaps, no
extra unsupported writes.

## Setup

```bash
keeper server --service-mode --port 4020 --api-key <token>
```

DSK defaults to `http://localhost:4020` and sends:

```text
api-key: <token>
```

Async queue endpoints used:

| Step | Endpoint |
|---|---|
| Submit | `POST /api/v2/executecommand-async` |
| Poll | `GET /api/v2/status/<request_id>` |
| Result | `GET /api/v2/result/<request_id>` |

File commands use FILEDATA inline JSON, for example:

```json
{"command":"pam project import --filename=FILEDATA","filedata":{"project":"acme"}}
```

## DSK Usage

```bash
export KEEPER_SERVICE_URL='http://localhost:4020'
export KEEPER_SERVICE_API_KEY='<token>'
export KEEPER_SERVICE_TIMEOUT=300

dsk --provider service plan manifest.yaml
dsk --provider service apply manifest.yaml --auto-approve
```

`KEEPER_SERVICE_URL` defaults to `http://localhost:4020`.
`KEEPER_SERVICE_API_KEY` is required. `KEEPER_SERVICE_TIMEOUT` defaults to 300
seconds.

## Docker / Terraform Pattern

The Keeper Terraform provider commonly runs Commander Service Mode as a sidecar
or local container, then points clients at the service URL and API key. Use the
same pattern for DSK: keep Commander login/config inside the service container,
publish only the service port to the DSK host, and inject the API key through
the environment.

## TLS

For production-like use, put Commander Service Mode behind TLS or a local TLS
terminating proxy and set:

```bash
export KEEPER_SERVICE_URL='https://commander-service.example.com'
```

Do not send the API key over an untrusted network without TLS. Rotate the key
like any other operator credential.

## Scope

Service Mode submits Commander commands over HTTP. It does not add new Commander
write or readback capability. Unsupported manifest keys remain plan conflicts
through the same detector used by `CommanderCliProvider`.
