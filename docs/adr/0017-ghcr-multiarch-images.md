# ADR 0017：通过 GitHub Actions 发布 GHCR 多架构镜像

- **状态**：已接受
- **决策时间**：2026-10-27
- **关系**：补充 ADR 0001；取代 ADR 0016 中默认在部署端构建的操作方式，保留其依赖分层与缓存策略。ADR 0016 其余决策仍有效。

## 背景

当前代码的 Compose 通过 `build` 在部署机器上构建前后端。
用户明确要求由 GitHub Actions 构建 amd64 和 ARM 镜像，并改为拉取预构建镜像部署。
本次将 ARM 支持明确为 `linux/arm64`，不包含 32 位 ARM。

## 决策

- 使用现有两个 Dockerfile，分别发布到 GHCR 的
  `ghcr.io/<owner>/<repo>-backend` 与 `ghcr.io/<owner>/<repo>-frontend`。
- GitHub Actions 使用 Buildx 和 QEMU 生成同时支持 `linux/amd64`、`linux/arm64`
  的镜像清单，并按服务隔离 GitHub Actions 构建缓存。
- `main` 推送更新 `latest`，`v*` Git 标签发布同名镜像标签；两者均发布完整提交
  SHA 标签。手动执行也可发布；Pull Request 仅构建，不登录或推送。
- 发布使用仓库内置 `GITHUB_TOKEN` 的 `packages: write` 权限，不新增发布密钥。
- Compose 只声明 `image`，默认使用上游 `latest`，允许通过镜像前缀与共用标签覆盖。
  不强制平台，由 Docker 按宿主机选择；保留端口、健康检查、环境变量和 SQLite 卷。
- 部署前先拉取两个镜像，再启动服务；生产建议固定版本或提交标签。

## 结果与权衡

部署机器无需编译环境，低配置 amd64/arm64 主机使用相同 Compose 文件。
代价是依赖 GitHub Actions 和 GHCR 的可用性，且 QEMU 模拟构建可能较慢。
两个服务独立发布，不保证 `latest` 原子更新；运维需确认两个任务成功，优先固定提交标签。
并发发布仍可能覆盖可变标签，提交标签用于明确选择构建来源。
既有 Python 依赖范围不因此变成锁定依赖，同一提交重新构建不保证逐字节一致。
GHCR 包需公开才能匿名拉取；私有部署须自行配置包读取权限和登录。
镜像回退不回退数据库，迁移兼容性与备份仍由部署者负责。

## 替代方案与依据

- 继续在部署端构建：不满足用户要求；保留显式本地构建命令供开发验证。
- 按架构发布独立标签：要求部署者手动选平台，采用多架构清单避免此负担。
- 使用原生双架构 runner 再合并清单：可减少模拟开销，但增加任务与清单合并流程；
  当前先使用较简单的 Buildx/QEMU 方案，未声称验证过其构建耗时。
- Docker Hub：仓库已托管在 GitHub，GHCR 可直接使用内置令牌，避免新增外部发布凭据。
