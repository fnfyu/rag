# Evidence RAG 前端工作台

Vue 3 + Vite + Element Plus 单页应用，提供知识库问答、索引链路状态与检索评测视图。

## 开发

```powershell
npm install
npm run dev
```

开发服务器把 `/api` 代理到后端（默认 `http://127.0.0.1:8000`，可用 `VITE_BACKEND_TARGET` 覆盖）。
需要在本地开发时携带 API key 时，在 `my-web/.env.local` 设置 `VITE_API_KEY`；生产构建不会把 key 打进 bundle。

## 构建

```powershell
npm run build
```

产物在 `dist/`，交由同源反向代理托管，并把 `/api` 转发到 FastAPI。

接口契约、检索策略与评测口径见仓库根目录的 [README.md](../README.md) 与 [docs/architecture.md](../docs/architecture.md)。
