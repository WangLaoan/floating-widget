# floating-widget — ETF 桌面监控组件

## 配置 Token

### 推送服务 Token (PushPlus)
PUSHPLUS_TOKEN = "f28d79309c2f4d1cb7d80cb06b7aa472"

### Tushare Token (备用)
TUSHARE_TOKEN = "6b61d8bd3450da7a437ba3f9484e5d44b120af3a58e8ca75c3dbda5b"

## 组件说明

桌面小组件 (`scripts/desktop_widget.py`) 提供：

- 系统托盘常驻，ETF 实时行情 + 估值温度
- 日线 MA120 偏离监控，偏离 < -4% 时 PushPlus 微信推送
- 价格跌破 日MA120×0.94 时托盘闪烁 + 气泡通知
- H30269 红利低波指数跟踪（AKShare 缓存）

## 推送规则

| 条件 | 动作 | 通道 |
|------|------|------|
| 价格 < 日MA120×0.94 | 托盘闪烁 + 气泡 | 桌面组件 |
| 偏离日MA120 < -4% | 桌面组件 → PushPlus | 桌面组件 |
| 偏离日MA120 < -4% | GitHub Actions → PushPlus | 云端 (每5分钟) |

## 双通道架构

```
桌面组件 (pythonw, 本地)
├── 实时行情 (新浪, 60s)
├── 托盘闪烁告警
└── PushPlus 推送

GitHub Actions (云端, 每5分钟)
├── 实时行情 (新浪)
├── MA120 偏离计算
└── PushPlus 推送
```

## 运行方式

```
cd floating-widget
python scripts/desktop_widget.py           # 正常启动
python scripts/desktop_widget.py --hidden  # 启动后隐藏到托盘
```
