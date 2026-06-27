# ContinuaCare — Frontend

The ContinuaCare web app: a marketing **landing page** and the **Care console** (TCM
dashboard) for the ContinuaCare hackathon project. Built from the Claude Design
prototypes (`design-reference/`), recreated as a real Vite + React + TypeScript app.

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
```

- `/`     → landing page
- `/demo` → Care console (patient roster + resizable detail drawer)

By default the app runs on **local mock/seed data** — no backend needed. The
"Simulate Discharge" button, KPI filters, code confirmation, and "Mark reviewed"
all work against in-memory state.

## Connecting the real backend

The data layer is ready to switch over with no UI changes:

1. Copy `.env.example` → `.env` and set:
   ```
   VITE_USE_MOCK=false
   VITE_API_URL=http://localhost:8000
   ```
2. `src/api.ts` already defines every endpoint from the master spec
   (`/patients`, `/episodes/{id}`, `/calls/trigger/{id}`, `/escalations/open`,
   `/episodes/{id}/generate-billing`, …). `getRoster()` fetches and adapts
   backend data into the console's view model via `toPatientVM()` — extend that
   adapter as the real API shape settles.

## Layout

```
src/
  main.tsx            app entry (Router)
  App.tsx             routes: "/" Landing, "/demo" Demo
  index.css           brand tokens, fonts, keyframes
  types.ts            UI model + backend DTOs (spec §3/§4)
  api.ts              axios client + endpoints + roster adapter (mock-gated)
  mockData.ts         seed roster + discharge scenarios
  store/useStore.ts   Zustand store: patients + UI state + actions
  lib/
    ui.tsx            css() inline-style helper + <H> hover wrapper
    viewModel.ts      pure builders for rows + detail drawer
  pages/
    Landing.tsx       marketing page (scroll-spy nav)
    Demo.tsx          the Care console
design-reference/     original Claude Design HTML (source of truth for pixels)
```

> Demo data · ContinuaCare hackathon prototype · not for clinical use.
