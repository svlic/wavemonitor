# WaveMonitor 设计系统

## 原则

- 深色金融监控面板：信息密度适中、层次清晰、状态一眼可读
- 单一强调色（青绿），避免紫蓝渐变等通用 AI 审美
- 动效仅用 `transform` / `opacity`，交互过渡 200ms

## 色彩

| Token | 值 | 用途 |
| --- | --- | --- |
| `--color-bg` | `#0c0f14` | 页面背景 |
| `--color-bg-elevated` | `#12161e` | 侧栏、表头 |
| `--color-panel` | `#161b24` | 卡片/面板 |
| `--color-border` | `#252b36` | 边框、分隔 |
| `--color-text` | `#e8eaed` | 正文 |
| `--color-muted` | `#8b95a8` | 标签、次要 |
| `--color-accent` | `#3dd68c` | 就绪、主按钮、品牌 |
| `--color-accent-muted` | `rgba(61, 214, 140, 0.12)` | 激活导航背景 |
| `--color-danger` | `#f07178` | 错误、删除 |

## 字体

- UI：`DM Sans`, system-ui, sans-serif
- 价格/数字：`JetBrains Mono`, ui-monospace, monospace；`font-variant-numeric: tabular-nums`

## 圆角与阴影

- 面板：`12px`，`box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.35)`
- 按钮：`8px`
- 输入：`8px`

## 布局

- 侧栏固定 `240px`，主内容区 `max-width: 1280px`，内边距 `2rem`
- 仪表盘：顶栏运行概览 + **全宽价格监控** 单表（运行状态与指标在上，价格表占主内容宽度）
- 告警与诊断：最近告警、Telegram 测试、数据源错误纵向分块
- 统计卡：2 / 3 / 6 列断点；数值等宽字体

## 组件状态

- 导航：当前路由 `.nav-link--active`
- 按钮：hover 提亮、`:focus-visible` 2px accent 描边
- 加载：`.loading-panel` + `.skeleton` 脉冲占位（仪表盘 / 运维 / 标的列表一致）
- 空态：`.empty-state`（虚线边框 + 居中）；带操作时用 `.empty-state--action`
- 状态胶囊：`.status-pill--ready` / `--idle`

## 布局补充

- 桌面侧栏：`position: sticky; height: 100dvh`；品牌区 `.sidebar-header` 为纵向 flex（窄屏改为横向）
- 主区垂直节奏：页面块间距用 `--space-panel`（1.25rem）
- 数字字体 token：`--font-mono`；`input[type=number]` 使用等宽 + `tabular-nums`

## 表格

- 通用：`.data-table`（告警、错误、标的列表）— 表头 uppercase muted、首列 `font-weight: 600`、行 hover 淡青绿
- 价格：`.price-monitor-table` — 与 data-table 同款表头；价格列 accent mono；指标列右对齐 mono

## 表单

- `.form-panel`：eyebrow + `.section-title` 标题层级
- 映射行：`.mapping-row` 五列 grid，`align-items: end`；窄屏单列
- 行内删除确认：`.inline-confirm` 浅红底区分危险操作

## 仪表盘 · 价格监控

- 容器：`.price-monitor-table-wrap` + `.price-monitor-table` 全宽扁平行表（每行 = 标的 × 来源）
- 列：标的、支撑/阻力、来源、价格、距支撑、距阻力、盈亏比、更新时间
- 数字：`.price-table-row__price` 使用 `--color-accent`；`.price-monitor__level-value` 用于支撑/阻力
- 窄屏：表格外层横向滚动（`min-width` 保证列可读），避免在卡片内嵌套滚动

## 告警与诊断 · 最近告警

- 区块：`.ops-layout` 内 `.ops-panel--wide` + `.data-table`
- 空态：「暂无最近告警。」与仪表盘价格空态分离
