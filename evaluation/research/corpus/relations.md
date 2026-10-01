# 消息链路明确关系

下列关系仅表示原文明确声明的依赖或用途；路径连接本身不证明故障必然传播，也不证明任意关系可以传递。

## 依赖关系表

| 主体 | 关系 | 客体 |
| --- | --- | --- |
| Orion | 依赖消息接入 | RelayMesh |
| RelayMesh | 使用持久队列 | AtlasQueue |
| AtlasQueue | 需要存储 | SSD持久卷 |
| ProbeWorker | 发送采集消息到 | RelayMesh |

## 非关系示例

Polaris 与 AtlasQueue 曾在同一份需求讨论中出现。共同出现并不表示 Polaris 依赖 AtlasQueue；不能从此句创建依赖关系。
