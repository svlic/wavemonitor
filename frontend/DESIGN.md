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
- 仪表盘网格：小屏 `minmax(360px, 1fr)`；≥1024px 为 12 列（状态 4 + 价格 8，告警 8 + 错误 4）
- 统计卡：2 / 3 / 6 列断点；数值等宽字体

## 组件状态

- 导航：当前路由 `.nav-link--active`
- 按钮：hover 提亮、`:focus-visible` 2px accent 描边
- 加载：`.skeleton` 脉冲占位

## 仪表盘 · 价格监控

- 标的区块：`.price-monitor__instrument`（内边距、边框、圆角 `--radius-panel`）
- 支撑/阻力：`.level-chip` + `.level-chip__label` / `.level-chip__value`（等宽数字用 JetBrains Mono）
- 来源卡片：`.price-source-card`，字段为 `.price-field`（标签 + 数值）；主价格 `.price-field__value--primary` 使用 `--color-accent`
- 响应式：`.price-monitor__sources` 为 `auto-fill`，单卡宽约 `11.25rem–14.5rem`；主价单独一行，三项指标横排