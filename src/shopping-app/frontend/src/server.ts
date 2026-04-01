import { Hono } from "hono";
import { serveStatic } from "hono/bun";

const app = new Hono();
const API_URL = process.env.API_URL || "http://shopping-backend:8000";

// Proxy /api requests to backend
app.all("/api/*", async (c) => {
  const url = new URL(c.req.url);
  const target = `${API_URL}${url.pathname}${url.search}`;
  const resp = await fetch(target, {
    method: c.req.method,
    headers: c.req.raw.headers,
    body:
      c.req.method !== "GET" && c.req.method !== "HEAD"
        ? await c.req.raw.text()
        : undefined,
  });
  return new Response(resp.body, {
    status: resp.status,
    headers: resp.headers,
  });
});

// Serve public files (manifest, sw.js)
app.use("/manifest.json", serveStatic({ path: "./src/public/manifest.json" }));
app.use("/sw.js", serveStatic({ path: "./src/public/sw.js" }));

// Serve built assets
app.get("/dist/*", serveStatic({ root: "./" }));
app.use("/index.js", serveStatic({ path: "./dist/index.js" }));
app.use("/app.css", serveStatic({ path: "./src/app/App.css" }));

// SPA fallback — serve index.html for all other routes
app.get("*", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="default" />
  <meta name="apple-mobile-web-app-title" content="Shopping" />
  <link rel="manifest" href="/manifest.json" />
  <link rel="stylesheet" href="/app.css" />
  <title>Shopping</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #fff; color: #1a1a1a; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/index.js"></script>
  <script>
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js');
    }
  </script>
</body>
</html>`);
});

export default {
  port: 3001,
  fetch: app.fetch,
};
