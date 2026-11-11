const APEX_HOST = "aetherengineapi.com.co";
const WWW_HOST = `www.${APEX_HOST}`;
const CALCULATOR_HOST = `calc.${APEX_HOST}`;
const PAGE_ASSET = "/wix-embed.html";
const CALCULATOR_ASSETS = new Map([
  ["/", "/calc/index.html"],
  ["/index.html", "/calc/index.html"],
  ["/calculator.css", "/calc/calculator.css"],
  ["/calculator.js", "/calc/calculator.js"],
]);
const CALCULATOR_ENDPOINTS = new Set([
  "/api/formulas/quantum",
  "/api/formulas/spin-network",
  "/api/formulas/los-link",
]);
const MAX_CALCULATOR_REQUEST_BYTES = 64_000;

function secureHeaders(extra = {}) {
  return new Headers({
    "Content-Security-Policy":
      "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    ...extra,
  });
}

function textResponse(body, status) {
  return new Response(body, {
    status,
    headers: secureHeaders({ "Content-Type": "text/plain; charset=utf-8" }),
  });
}

function calculatorHeaders(extra = {}) {
  return secureHeaders({
    "Cache-Control": "no-store",
    "Content-Security-Policy":
      "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    ...extra,
  });
}

function calculatorTextResponse(body, status, extra = {}) {
  return new Response(body, {
    status,
    headers: calculatorHeaders({
      "Content-Type": "text/plain; charset=utf-8",
      ...extra,
    }),
  });
}

async function calculatorAsset(request, env, url) {
  const assetPath = CALCULATOR_ASSETS.get(url.pathname);
  if (!assetPath) return calculatorTextResponse("Not found.", 404);
  if (request.method !== "GET" && request.method !== "HEAD") {
    return calculatorTextResponse("Method not allowed.", 405, { Allow: "GET, HEAD" });
  }

  const assetUrl = new URL(assetPath, url);
  const assetResponse = await env.ASSETS.fetch(
    new Request(assetUrl, { method: "GET" }),
  );
  if (!assetResponse.ok) {
    return calculatorTextResponse("Calculator interface is unavailable.", 502);
  }
  return new Response(request.method === "HEAD" ? null : assetResponse.body, {
    status: 200,
    headers: calculatorHeaders({
      "Content-Type":
        assetResponse.headers.get("Content-Type") || "application/octet-stream",
    }),
  });
}

async function calculatorApi(request, env, url) {
  if (!CALCULATOR_ENDPOINTS.has(url.pathname)) {
    return calculatorTextResponse("Not found.", 404);
  }
  if (request.method !== "POST") {
    return calculatorTextResponse("Method not allowed.", 405, { Allow: "POST" });
  }
  if (
    request.headers.get("content-type", "").split(";")[0] !== "application/json"
  ) {
    return calculatorTextResponse("JSON requests required.", 415);
  }
  const contentLength = request.headers.get("content-length");
  if (
    contentLength !== null &&
    Number(contentLength) > MAX_CALCULATOR_REQUEST_BYTES
  ) {
    return calculatorTextResponse("Request exceeds the 64 KB limit.", 413);
  }
  if (!env.API_ORIGIN || !env.API_TOKEN) {
    return calculatorTextResponse("Calculator service is not configured.", 503);
  }

  let origin;
  try {
    origin = new URL(env.API_ORIGIN);
  } catch {
    return calculatorTextResponse("Calculator service is not configured.", 503);
  }
  if (
    origin.protocol !== "https:" ||
    origin.username ||
    origin.password ||
    origin.pathname !== "/" ||
    origin.search ||
    origin.hash
  ) {
    return calculatorTextResponse("Calculator service is not configured.", 503);
  }

  const upstreamUrl = new URL(url.pathname, origin);
  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Bearer ${env.API_TOKEN}`,
    "Content-Type": "application/json",
  });
  let upstream;
  try {
    upstream = await fetch(upstreamUrl, {
      method: "POST",
      headers,
      body: request.body,
      redirect: "manual",
    });
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
    console.error("Calculator origin could not be reached.", error.message);
    return calculatorTextResponse("Calculator origin could not be reached.", 502);
  }

  if (upstream.status >= 300 && upstream.status < 400) {
    return calculatorTextResponse("Calculator origin returned a redirect.", 502);
  }
  if (upstream.status >= 500) {
    return calculatorTextResponse("Calculator origin returned an error.", 502);
  }
  const contentType = upstream.headers.get("content-type") || "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return calculatorTextResponse("Calculator origin returned an invalid response.", 502);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: calculatorHeaders({ "Content-Type": "application/json" }),
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.hostname === CALCULATOR_HOST) {
      if (env.CALCULATOR_ACCESS_ENABLED !== "true") {
        return calculatorTextResponse("Calculator access is not enabled.", 404);
      }
      if (url.pathname.startsWith("/api/formulas/")) {
        return calculatorApi(request, env, url);
      }
      return calculatorAsset(request, env, url);
    }

    if (url.hostname === WWW_HOST) {
      url.hostname = APEX_HOST;
      url.protocol = "https:";
      return new Response(null, {
        status: 308,
        headers: secureHeaders({ Location: url.toString() }),
      });
    }

    if (url.pathname !== "/") {
      return textResponse("Not found.", 404);
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed.", {
        status: 405,
        headers: secureHeaders({
          Allow: "GET, HEAD",
          "Content-Type": "text/plain; charset=utf-8",
        }),
      });
    }

    const assetUrl = new URL(PAGE_ASSET, request.url);
    const assetResponse = await env.ASSETS.fetch(
      new Request(assetUrl, { method: "GET" }),
    );
    if (!assetResponse.ok) {
      return textResponse("Site content is unavailable.", 502);
    }

    const embed = await assetResponse.text();
    const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Documentation for the local-first Aether Engine Python REST API. This public page does not provide API access.">
  <meta name="color-scheme" content="dark">
  <meta property="og:title" content="Aether Engine API | Local-First Python REST API">
  <meta property="og:description" content="Documentation for the local-first Aether Engine Python REST API.">
  <meta property="og:url" content="https://${APEX_HOST}/">
  <link rel="canonical" href="https://${APEX_HOST}/">
  <title>Aether Engine API | Local-First Python REST API</title>
</head>
<body>
${embed}
</body>
</html>`;
    const headers = secureHeaders({
      "Cache-Control": "public, max-age=300, s-maxage=3600",
      "Content-Type": "text/html; charset=utf-8",
    });

    return new Response(request.method === "HEAD" ? null : html, { headers });
  },
};
