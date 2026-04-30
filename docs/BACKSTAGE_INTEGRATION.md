# Backstage Integration

The DSK Backstage scaffold exposes `dsk plan --json` through a backend router and
renders the plan summary in a frontend card. It is an offline scaffold: it does
not mutate Keeper state, and the backend only reads the configured manifest.

## Packages

Copy or vendor these local packages into a Backstage app:

- `backstage-plugin-dsk` (`@internal/plugin-dsk`) for the frontend card.
- `backstage-plugin-dsk-backend` (`@internal/plugin-dsk-backend`) for the API
  route that shells out to the DSK CLI.

Install them in the Backstage app workspace with the same package manager used
by the portal, then register the backend plugin:

```ts
// packages/backend/src/index.ts
backend.add(import('@internal/plugin-dsk-backend'));
```

## Backend Configuration

Configure the DSK binary and manifest path in `app-config.yaml`:

```yaml
dsk:
  binaryPath: dsk
  manifestPath: /srv/backstage/dsk/environment.yaml
  timeoutMs: 30000
  maxBufferBytes: 1048576
```

The backend mounts a router at `/api/dsk` and provides:

- `GET /api/dsk/health`
- `GET /api/dsk/plan`
- `GET /api/dsk/plan?manifestPath=/path/to/manifest.yaml`

The plan endpoint runs:

```bash
dsk plan /path/to/manifest.yaml --json
```

DSK exits `0` for clean plans, `2` for changes present, and `4` for conflicts.
The router treats all three as successful plan reads and returns the parsed JSON
plus `exitCode`.

## Frontend Card

Add the plan card where the platform team expects Keeper resource state, such as
an entity overview page:

```tsx
import { DskPlanCard } from '@internal/plugin-dsk';

export const overviewContent = (
  <Grid container spacing={3}>
    <Grid item xs={12} md={6}>
      <DskPlanCard title="Keeper Resource Plan" />
    </Grid>
  </Grid>
);
```

The card calls `/api/dsk/plan` by default and displays the plan summary counts:
`create`, `update`, `delete`, `conflict`, and `noop`.

To point a card at a different manifest without changing global config:

```tsx
<DskPlanCard manifestPath="/srv/backstage/dsk/team-a.yaml" />
```

## Screenshot

Placeholder: add a screenshot of the Backstage entity page with the DSK plan card
after the plugin is mounted in a portal app.

## Output Format Note

`dsk plan --format json` and `dsk plan --format table` are accepted aliases for
the existing renderers. `--format backstage` is reserved as a future integration
format and currently returns a capability error instead of silently emitting a
partial contract.
