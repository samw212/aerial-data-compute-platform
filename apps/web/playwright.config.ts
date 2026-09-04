import { defineConfig } from "@playwright/test";

/* End-to-end over the running stack. Point ADCP_E2E_URL at nginx on the
 * instance, or at the Vite dev server (which proxies to the API). */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.ADCP_E2E_URL ?? "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    video: "off",
  },
  outputDir: "./e2e/.artifacts",
  reporter: [["list"]],
});
