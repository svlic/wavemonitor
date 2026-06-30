# Docker

- **后端**：`backend/Dockerfile`，Uvicorn 监听 `8000`
- **前端**：`frontend/Dockerfile` + `frontend/docker/nginx.conf`，容器内 Nginx `8080`，反代 `/api` 与 `/health` 到 `backend:8000`
- **编排**：仓库根目录 `docker compose up --build`，Web 访问 **http://localhost:54002**