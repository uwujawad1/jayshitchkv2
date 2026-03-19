import express, { type Express } from "express";
import { createProxyMiddleware } from "http-proxy-middleware";

const app: Express = express();

app.use(
  createProxyMiddleware({
    target: "http://localhost:5000",
    changeOrigin: false,
    ws: true,
  })
);

export default app;
