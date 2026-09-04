# End-to-end tests

The Playwright suite lives in `apps/web/e2e` so it shares the web app's
node_modules. Run it with `make test-e2e` (or `npx playwright test` in apps/web)
against a running stack: `ADCP_E2E_URL=http://<host>:6006`.
