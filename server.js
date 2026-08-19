const http = require("http");

const htmlPage = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Diplomka</title>
    <style>
      body {
        font-family: sans-serif;
        margin: 16px;
      }

      .results {
        display: flex;
        gap: 16px;
      }

      .panel {
        flex: 1;
        min-width: 0;
      }

      pre {
        white-space: pre-wrap;
        word-break: break-word;
      }
    </style>
  </head>
  <body>
    <form id="diplomka-form">
      <input
        id="pid"
        name="pid"
        type="text"
        placeholder="pid"
        style="padding: 10px;font-size: 16px;"
        required
      />
      <button
        type="submit"
        style="padding: 10px;font-size: 16px;"
      >
        Search
      </button>
    </form>

    <div class="results">
      <section class="panel">
        <h2>OpenAIRE</h2>
        <pre id="openaire-response"></pre>
      </section>

      <section class="panel">
        <h2>Zenodo</h2>
        <pre id="zenodo-response"></pre>
      </section>
    </div>

    <script>
      const form = document.getElementById("diplomka-form");
      const pidField = document.getElementById("pid");
      const openaireOutput = document.getElementById("openaire-response");
      const zenodoOutput = document.getElementById("zenodo-response");

      form.addEventListener("submit", async (event) => {
        event.preventDefault();

        openaireOutput.textContent = "Loading...";
        zenodoOutput.textContent = "Loading...";

        try {
          const result = await fetch("/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ pid: pidField.value }),
          });

          const data = await result.json();

          if (!result.ok) {
            openaireOutput.textContent = data.error || "Request failed.";
            zenodoOutput.textContent = data.error || "Request failed.";
            return;
          }

          openaireOutput.textContent = JSON.stringify(data.openaire, null, 2);
          zenodoOutput.textContent = JSON.stringify(data.zenodo, null, 2);
        } catch (error) {
          openaireOutput.textContent = "Request failed.";
          zenodoOutput.textContent = "Request failed.";
        }
      });
    </script>
  </body>
</html>
`;

class HttpError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.statusCode = statusCode;
  }
}

function sendHtml(res, body) {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(body);
}

function sendJson(res, statusCode, body) {
  res.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body, null, 2));
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";

    req.on("data", (chunk) => {
      body += chunk;
    });

    req.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch (error) {
        reject(error);
      }
    });

    req.on("error", reject);
  });
}

async function fetchResearchProductsByPid(pid) {
  const url = new URL("https://api.openaire.eu/graph/v3/research-products");
  url.searchParams.set("pid", pid);

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new HttpError(502, "OpenAIRE request failed.");
  }

  return response.json();
}

function extractZenodoRecordIdFromPid(pid) {
  const match = pid.match(/^10\.5281\/zenodo\.(\d+)$/i);
  return match ? match[1] : null;
}

async function fetchZenodoRecordByPid(pid) {
  const recordId = extractZenodoRecordIdFromPid(pid);

  if (!recordId) {
    throw new HttpError(
      400,
      "Zenodo fetch currently supports only pid in format 10.5281/zenodo.<recordId>."
    );
  }

  const response = await fetch(`https://zenodo.org/api/records/${recordId}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (response.status === 404) {
    throw new HttpError(404, "Zenodo record was not found.");
  }

  if (!response.ok) {
    throw new HttpError(502, "Zenodo request failed.");
  }

  return response.json();
}

const server = http.createServer(async (req, res) => {
  // GET /
  if (req.method === "GET" && req.url === "/") {
    sendHtml(res, htmlPage);
    return;
  }

  // POST /
  if (req.method === "POST" && req.url === "/") {
    try {
      const body = await readRequestBody(req);
      const pid = typeof body.pid === "string" ? body.pid.trim() : "";

      if (!pid) {
        throw new HttpError(400, "PID is required.");
      }

      const [openaireResponse, zenodoResponse] = await Promise.all([
        fetchResearchProductsByPid(pid),
        fetchZenodoRecordByPid(pid),
      ]);

      sendJson(res, 200, {
        pid,
        openaire: openaireResponse,
        zenodo: zenodoResponse,
      });
    } catch (error) {
      const statusCode = error.statusCode ?? 400;
      const message = error.message || "Invalid request body";

      sendJson(res, statusCode, {
        error: message,
      });
    }
    return;
  }

  sendJson(res, 404, {
    error: "Not found",
  });
});

server.listen(8080, "0.0.0.0");