# ADR 0011：将最新行情状态保存在进程内存

- **状态**：已接受
- **决策时间**：2026-09-20

## 背景

此前每次成功轮询和供应商错误都会写入 `PriceObservation`，查询 API 再从 SQLite 中选择
最新成功或最新失败记录。系统还需每轮删除三天前的观测。Git 历史只记录了改动结果，
没有记录明确动机。

减少 SQLite 高频写入、磁盘增长和清理逻辑是与 diff 一致的历史推断，但不作为已确认
原因。项目所有者确认，可以接受进程重启后暂时没有最新价格和 source error。

## 决策

- 使用进程级、带锁的 `LatestPriceStore` 保存每个 Source Mapping 的：
  - 最新成功价格和时间；
  - 最后尝试时间；
  - 最后错误。
- 成功轮询清除当前错误；失败轮询保留此前的最新成功价格并更新错误。
- `/api/prices/latest`、Instrument status 和 `/api/source-errors` 从内存读取。
- 进程重启后状态为空，等待下一次对应 source 轮询。
- Instrument 或 Source Mapping 删除时同步删除相应内存条目。
- `observations_written` 响应字段为兼容保留，含义改为成功的内存快照更新次数。
- AlertEvent、LastRuleState 和 TelegramDelivery 仍保存在 SQLite；只有瞬时行情和 source
  error 转为易失状态。

## 结果

### 正面影响

- 正常轮询不再为行情快照和错误产生持续 SQLite 写入。
- 不再需要三天观测清理和“最新行”查询。
- 错误不会覆盖最后一次成功价格。

### 负面影响和限制

- 重启会丢失最新行情和 source error，Dashboard 在首次成功轮询前显示待获取。
- 不能从主数据库恢复历史价格或分析供应商历史稳定性。
- 多进程时每个进程拥有不同快照，再次强化单 worker 限制。
- `observations_written` 名称与实际语义不一致，是兼容性债务。

## 后续决策

[ADR 0013](0013-remove-legacy-price-observation-storage.md) 完成了该迁移：删除
`PriceObservation` ORM 模型和死清理路径，并在 SQLite 启动迁移中删除遗留表。旧行情观测
不再属于需要保留的业务记录。

## 历史依据

- `3f8f100`：增加 `LatestPriceStore`，停止写入和查询 PriceObservation 最新状态。
- `25cfa44`：在 API 契约中明确内存状态、重启行为和兼容字段语义。
- 项目所有者确认：接受重启后的短暂空状态。
