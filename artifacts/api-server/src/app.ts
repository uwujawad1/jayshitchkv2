import express, { type Express, type Request, type Response } from "express";
import http from "http";

const app: Express = express();

const HITCHK_PORT = 23863;

app.use((req: Request, res: Response) => {
  const options: http.RequestOptions = {
    hostname: "localhost",
    port: HITCHK_PORT,
    path: req.url,
    method: req.method,
    headers: {
      ...req.headers,
      "x-forwarded-host": req.headers["x-forwarded-host"] || req.headers["host"] || "",
    },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 200, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on("error", (err) => {
    if (!res.headersSent) {
      res.status(502).json({ message: "Proxy error: " + err.message });
    }
  });

  req.pipe(proxyReq, { end: true });
});

export default app;
