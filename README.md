# salon-booking：美甲店预约系统

一个小型后端项目，解决美甲店的预约冲突问题：店里有 3 位技师和数量有限的设备，预约时既不能让同一位技师同时服务两位客人，也不能让设备超过库存。

项目只用 Python 标准库，**不需要安装任何第三方依赖**。数据保存在内存里，适合学习、面试演示和作为真实系统的原型。

---

## 目录

1. [这个项目解决什么问题](#1-这个项目解决什么问题)
2. [快速开始](#2-快速开始)
3. [项目结构](#3-项目结构)
4. [业务规则详解](#4-业务规则详解)
5. [HTTP 接口说明](#5-http-接口说明)
6. [完整操作演示](#6-完整操作演示)
7. [错误码一览](#7-错误码一览)
8. [在代码里直接调用](#8-在代码里直接调用)
9. [实现原理](#9-实现原理)
10. [测试说明](#10-测试说明)
11. [常见问题](#11-常见问题)
12. [局限与后续方向](#12-局限与后续方向)

---

## 1. 这个项目解决什么问题

### 店里有什么

**技师**：T1、T2、T3。每位技师同一时间只能服务一位客人。

**设备**：

| 设备 | 代号 | 数量 |
| --- | --- | --- |
| 光疗灯 | `uv_lamp` | 2 |
| 手部 SPA 机 | `spa_machine` | 1 |

**服务**：

| 服务 | 代号 | 时长 | 需要的设备 |
| --- | --- | --- | --- |
| 基础美甲 | `basic_manicure` | 30 分钟 | 无 |
| 凝胶美甲 | `gel_manicure` | 60 分钟 | 1 盏 `uv_lamp` |
| 光疗延长 | `gel_extension` | 90 分钟 | 1 盏 `uv_lamp` |
| 手部 SPA | `hand_spa` | 60 分钟 | 1 台 `spa_machine` |

一次预约会在**整个服务时长内**一直占用所需设备。

### 提供两个功能

1. **创建预约**：给定技师、服务、开始时间，检查能不能约；能约就记下来，不能约就告诉你是技师冲突还是哪个设备不够。
2. **查询可用时段**：给定技师、日期、服务，列出这一天所有能开始这项服务的时间点，同时考虑技师的档期和设备的占用情况。

---

## 2. 快速开始

### 2.1 准备环境

需要 **Python 3.10 或更高版本**。先检查版本：

```powershell
python --version
```

如果显示的版本低于 3.10，或者提示找不到命令，请到 python.org 安装新版。Windows 上有时命令是 `py` 而不是 `python`，下面的命令里把 `python` 换成 `py` 即可。

如果你用 [uv](https://docs.astral.sh/uv/)，把下面所有 `python` 换成 `uv run python` 即可，本项目没有依赖，不需要执行 `uv sync`。

### 2.2 下载并进入项目目录

解压 `salon-booking.zip`，在 PowerShell 里进入解压出来的目录：

```powershell
cd salon-booking
```

**后面所有命令都要在这个目录（项目根目录）下执行。** 在别的目录执行会出现 `No module named salon`。

### 2.3 跑测试，确认一切正常

```powershell
python -m unittest discover -s tests -t . -v
```

正常的结果最后几行是：

```
Ran 20 tests in 0.0xxs

OK
```

### 2.4 跑演示脚本

演示脚本不需要启动服务，直接调用核心函数：

```powershell
python demo.py
```

应该看到类似下面的输出：

```
1) T1 约凝胶美甲 10:00 -> OK
2) T2 约凝胶美甲 10:00 -> OK
3) T3 约凝胶美甲 10:00 -> EQUIPMENT_CONFLICT [{'type': 'equipment', 'equipment': 'uv_lamp', 'capacity': 2, 'peak_in_use': 2, 'needed': 1}]
4) T3 当天凝胶美甲可约起点（前 8 个）: ['09:00', '11:00', '11:15', '11:30', '11:45', '12:00', '12:15', '12:30']
   其中包含 09:00、不含 09:15~10:45、含 11:00: True True True True
```

这段输出讲了一个故事：T1 和 T2 在同一时间都约了凝胶美甲，两盏灯被占满；T3 本人是空闲的，但没有第三盏灯，所以 T3 也约 10:00 会失败；查询 T3 的可用时段，会发现 09:15 到 10:45 这些起点都消失了。

### 2.5 启动 HTTP 服务

```powershell
python -m salon.server
```

看到下面这行就表示服务已经在运行：

```
Salon booking API on http://127.0.0.1:8000
```

这个窗口要一直开着。按 `Ctrl + C` 停止服务。要测试接口，请**另开一个 PowerShell 窗口**（见第 6 节）。

如果 8000 端口被占用，可以换一个端口，例如 9000：

```powershell
python -c "from salon.server import main; main(9000)"
```

---

## 3. 项目结构

```
salon-booking/
├── salon/
│   ├── __init__.py
│   ├── booking.py        核心逻辑：时间区间工具、冲突检查、创建预约、查询时段
│   └── server.py         最小 HTTP 服务，把核心逻辑包装成 REST 接口
├── tests/
│   ├── __init__.py
│   └── test_booking.py   20 个单元测试
├── demo.py               不起服务的演示脚本
├── pyproject.toml        项目信息（没有依赖）
├── .gitignore
└── README.md
```

两个核心文件的分工：

- `booking.py` 是**业务层**：只管规则，不知道 HTTP 的存在。测试直接测它，不需要启动服务器。
- `server.py` 是**接口层**：解析请求、检查参数格式、调用业务层、把结果转成 HTTP 状态码和 JSON。

---

## 4. 业务规则详解

### 4.1 时间区间：左闭右开

一个预约占用的时间是 `[开始, 结束)`，包含开始时刻，不包含结束时刻。

所以 10:00–11:00 的预约和 11:00–12:00 的预约**不冲突**（首尾相接），可以连着约。

### 4.2 创建预约要同时满足两个条件

在整个服务时长内：

1. **技师没有重叠的预约。**
2. **所需设备在每一个时刻都够用**：每个时刻正在使用的设备数量，加上这次预约要用的数量，不能超过库存。

### 4.3 为什么强调“每一个时刻”

只检查“新预约开始那一刻有几盏灯在用”是**错误**的。看这个例子（uv_lamp 一共 2 盏）：

| 预约 | 时间 | 用灯 |
| --- | --- | --- |
| A：T1 光疗延长 | 10:00–11:30 | 1 盏 |
| B：T2 凝胶美甲 | 11:00–12:00 | 1 盏 |
| 新预约：T3 凝胶美甲 | 10:30–11:30 | 要 1 盏 |

时间轴上灯的使用情况：

```
时间      10:00    10:30    11:00    11:30    12:00
A  ██████████████████████████████████
B                           ██████████████████████
新                 ████████████████████
在用灯数    1        1        2        1        0
```

新预约 10:30 开始时，只有 A 在用，灯数是 1，看起来还有空位。但到 11:00，B 也开始了，灯数变成 2，新预约又要占 1 盏，11:00–11:30 这段就会变成 3 盏，超过库存 2。所以这一单必须被拒绝。

本项目的做法是：设备的占用数只会在某个预约**开始**的时刻上升，所以只需要检查新预约的起点，以及新预约时间窗口内每一个已有预约的开始时刻。这就是代码里的 `peak_usage` 函数。

### 4.4 营业时间和时间粒度

- 营业时间 09:00–19:00，预约必须在营业时间内**结束**。例如 60 分钟的服务，最晚 18:00 开始。
- 查询可用时段时，候选起点每 15 分钟一个（09:00、09:15、09:30……）。
- 创建预约时只要求时间在营业时间内，不强制对齐 15 分钟。

### 4.5 冲突原因的返回

预约失败时会告诉你原因。如果技师和设备同时冲突，两个原因都会返回，技师冲突排在前面。

### 4.6 幂等：重复提交不会重复预约

创建预约时必须带一个 `Idempotency-Key`（由客户端生成的任意唯一字符串）。用同一个 key 重复提交，服务会返回**第一次的结果**，不会再建一单。这样用户在网络不好时连点按钮、或客户端自动重试，都不会产生重复预约。

---

## 5. HTTP 接口说明

服务地址：`http://127.0.0.1:8000`，请求和返回都是 JSON。

### 5.1 创建预约

`POST /bookings`

**请求头**

| 名称 | 是否必填 | 说明 |
| --- | --- | --- |
| `Idempotency-Key` | 是 | 每次“用户点击预约”换一个新值，例如 `k1`、`k2`；重试时保持不变 |

**请求体**

```json
{
  "technician_id": "T1",
  "service_id": "gel_manicure",
  "start_at": "2026-10-02T10:00:00"
}
```

| 字段 | 说明 |
| --- | --- |
| `technician_id` | 技师代号，`T1`、`T2` 或 `T3` |
| `service_id` | 服务代号，见 1 节的服务表 |
| `start_at` | 开始时间，ISO 8601 格式。带时区偏移（如 `-04:00`）也可以，但会被去掉偏移，按门店本地时间处理 |

**成功：HTTP 201**

```json
{
  "booking_id": "730dabd0",
  "technician_id": "T1",
  "service_id": "gel_manicure",
  "start_at": "2026-10-02T10:00:00",
  "end_at": "2026-10-02T11:00:00",
  "equipment": [{"equipment_id": "uv_lamp", "quantity": 1}],
  "status": "confirmed"
}
```

`booking_id` 每次是随机生成的，你看到的值会不一样。

**失败：HTTP 409（设备不足）**

```json
{
  "error": {
    "code": "EQUIPMENT_CONFLICT",
    "message": "time slot not available",
    "details": [
      {"type": "equipment", "equipment_id": "uv_lamp", "capacity": 2, "peak_in_use": 2, "needed": 1}
    ]
  }
}
```

`details` 的含义：`uv_lamp` 一共 `capacity` = 2 盏，这段时间内最多同时有 `peak_in_use` = 2 盏在用，这次还需要 `needed` = 1 盏，2 + 1 > 2，所以失败。

**失败：HTTP 409（技师冲突）**

`details` 里是 `{"type": "technician", "technician": "T1", "booking_id": "..."}`，`booking_id` 是和你冲突的那一单。

### 5.2 查询可用时段

`GET /technicians/{技师代号}/availability?date=日期&service_id=服务代号`

例如：

```
GET /technicians/T3/availability?date=2026-10-02&service_id=gel_manicure
```

**成功：HTTP 200**

```json
{
  "technician_id": "T3",
  "date": "2026-10-02",
  "service_id": "gel_manicure",
  "duration_min": 60,
  "slots": ["2026-10-02T09:00:00", "2026-10-02T09:15:00", "2026-10-02T09:30:00"]
}
```

`slots` 是所有可以开始这项服务的时间点。如果一个都没有，`slots` 是空数组 `[]`，状态码仍然是 200。

这个接口和创建预约共用同一套检查，所以**列表里出现的时间，实际创建一定成功；没出现的时间，创建一定失败**（测试里有专门的用例验证这一点）。

---

## 6. 完整操作演示

按下面的顺序走一遍，能完整看到“设备被占满”是怎么影响查询结果的。

**先确认服务已经在另一个窗口启动**（见 2.5）。下面所有命令都在**新开的 PowerShell 窗口**里执行。

### 第 1 步：查询 T3 的可用时段（还没人预约）

```powershell
curl.exe "http://127.0.0.1:8000/technicians/T3/availability?date=2026-10-02&service_id=gel_manicure"
```

`slots` 里从 `09:00` 开始，每 15 分钟一个，一直到 `18:00`，共 37 个。

### 第 2 步：T1 预约 10:00 的凝胶美甲

```powershell
$body = @{ technician_id = "T1"; service_id = "gel_manicure"; start_at = "2026-10-02T10:00:00" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/bookings" -Headers @{ "Idempotency-Key" = "k1" } -ContentType "application/json" -Body $body
```

返回预约详情，状态是 `confirmed`。

### 第 3 步：T2 也预约 10:00 的凝胶美甲

把上一步的 `T1` 改成 `T2`，`Idempotency-Key` 改成 `k2`：

```powershell
$body = @{ technician_id = "T2"; service_id = "gel_manicure"; start_at = "2026-10-02T10:00:00" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/bookings" -Headers @{ "Idempotency-Key" = "k2" } -ContentType "application/json" -Body $body
```

也成功。现在 10:00–11:00 两盏灯都被占满了。

### 第 4 步：再查 T3 的可用时段

```powershell
curl.exe "http://127.0.0.1:8000/technicians/T3/availability?date=2026-10-02&service_id=gel_manicure"
```

这次 `slots` 变成：`09:00`，然后跳到 `11:00`、`11:15`、`11:30`……

- `09:00` 还在：09:00–10:00 刚好在灯被占用之前结束。
- `09:15` 到 `10:45` 都没了：这些时段会和 10:00 起被占满的两盏灯重叠。
- `11:00` 回来了：10:00–11:00 的预约在 11:00 结束，灯释放了。

T3 本人一整天都是空闲的，被挡住的原因完全是设备不够。

### 第 5 步：T3 硬约 10:00，看冲突提示

`Invoke-RestMethod` 遇到 409 会直接报错，看不到返回内容。这里用 `curl.exe` 配合一个 JSON 文件，可以看到完整的冲突信息。

先把请求内容写进文件：

```powershell
Set-Content -Path booking.json -Value '{"technician_id":"T3","service_id":"gel_manicure","start_at":"2026-10-02T10:00:00"}' -Encoding ascii
```

再发送请求：

```powershell
curl.exe -i -X POST "http://127.0.0.1:8000/bookings" -H "Idempotency-Key: k3" -d "@booking.json"
```

`-i` 会显示 HTTP 状态行。你会看到 `409` 和 `EQUIPMENT_CONFLICT`，`details` 里写着 `uv_lamp` 库存 2、峰值占用 2。

### 第 6 步：试试幂等

把第 2 步的命令原样再执行一次（`Idempotency-Key` 仍然是 `k1`）。会返回**同一个 `booking_id`**，并没有多出一单，也不会因为 T1 已经有这一单而报技师冲突。

### macOS / Linux 用户

```bash
curl -X POST localhost:8000/bookings -H 'Idempotency-Key: k1' \
  -d '{"technician_id":"T1","service_id":"gel_manicure","start_at":"2026-10-02T10:00:00"}'

curl "localhost:8000/technicians/T3/availability?date=2026-10-02&service_id=gel_manicure"
```

---

## 7. 错误码一览

| HTTP 状态码 | `code` | 含义 |
| --- | --- | --- |
| 201 | （成功） | 预约已创建 |
| 400 | `INVALID_REQUEST` | 缺少字段，或时间、日期格式不对，或请求体不是合法 JSON |
| 400 | `MISSING_IDEMPOTENCY_KEY` | 创建预约时没带 `Idempotency-Key` 请求头 |
| 404 | `UNKNOWN_TECHNICIAN` | 技师代号不存在 |
| 404 | `UNKNOWN_SERVICE` | 服务代号不存在 |
| 404 | `NOT_FOUND` | 路径不存在，或查询时技师/服务代号不存在 |
| 409 | `TECHNICIAN_CONFLICT` | 技师在这段时间已有预约（也可能同时有设备冲突，见 `details`） |
| 409 | `EQUIPMENT_CONFLICT` | 某个设备在这段时间内的某一刻已经满了 |
| 422 | `OUTSIDE_HOURS` | 预约超出营业时间（09:00 之前开始，或 19:00 之后才结束） |

---

## 8. 在代码里直接调用

不用启动服务，直接在 Python 里使用核心类：

```python
from datetime import date, datetime
from salon.booking import SalonService

s = SalonService()

# 创建预约
first = s.create_booking("T1", "gel_manicure", datetime(2026, 10, 2, 10, 0))
print(first.ok)         # True
print(first.booking)    # Booking(id=..., technician='T1', ...)

# 失败时看原因
r = s.create_booking("T1", "basic_manicure", datetime(2026, 10, 2, 10, 15))
print(r.ok, r.code)     # False TECHNICIAN_CONFLICT
print(r.conflicts)      # 冲突明细列表

# 查询可用时段
slots = s.available_slots("T2", date(2026, 10, 2), "hand_spa")
print([t.strftime("%H:%M") for t in slots])

# 取消第一单，释放技师和设备
print(s.cancel_booking(first.booking.id))   # True
```

自定义技师、设备、服务和营业时间：

```python
s = SalonService(
    technicians=["A", "B"],
    equipment={"uv_lamp": 1},
    services={"gel": {"minutes": 45, "needs": {"uv_lamp": 1}}},
)
```

---

## 9. 实现原理

### 9.1 一个检查函数，两个接口共用

`SalonService._check(技师, 服务, 开始时间)` 是核心：它依次检查输入、营业时间、技师重叠、各种设备的峰值占用，返回结果。

- 创建预约调用它一次，通过才写入。
- 查询可用时段对当天每一个候选起点各调用一次。

两个接口用的是同一份判断逻辑，所以不会出现“查询说能约、实际约不上”的矛盾。

### 9.2 设备检查：扫描线

对每一种需要的设备：

1. 找出所有和新预约时间窗口重叠的、使用这种设备的已有预约。
2. 在新预约的起点，以及窗口内每个已有预约的开始时刻，数一数同时有多少个预约在占用这种设备，取最大值，叫做峰值。
3. 如果 `峰值 + 这次需要的数量 > 库存`，这种设备就冲突。

### 9.3 并发：加锁保证不超卖

“检查有没有空位”和“把预约记下来”必须是一个不可分割的整体。否则两个同时到来的请求会都看到“还剩一盏灯”，然后都写入，造成超卖。

内存版用一把互斥锁（`threading.Lock`）把检查和写入包在一起。测试里用 20 个线程同时抢 2 盏灯，恰好成功 2 单。

在真实数据库里，对应的做法是：在一个事务里先锁住设备类型那一行（`SELECT ... FOR UPDATE`），再检查、再插入；技师不重叠可以再用数据库的排他约束兜底。详细设计见需求报告第 4、7 节。

### 9.4 取消预约

取消只是把预约状态改成 `cancelled`。检查冲突时只统计状态为 `confirmed` 的预约，所以取消后，该时段的技师和设备立刻可以被别人预约。

---

## 10. 测试说明

运行：

```powershell
python -m unittest discover -s tests -t . -v
```

测试共 20 个，分组如下：

| 分组 | 验证的内容 |
| --- | --- |
| 区间工具 | 首尾相接不算重叠；扫描线峰值计算正确 |
| 创建预约 | 成功并算对结束时间；技师重叠被拒；第 3 盏灯被拒；**“每一个时刻”场景**；设备在结束时刻释放；SPA 机只有 1 台；无设备服务不受影响；技师和设备同时冲突；营业时间边界；未知技师或服务；幂等；取消后释放 |
| 查询时段 | 空白一天的时段数量；技师档期被排除；设备争用被排除；**随机预约 25 单后，查询结果与创建结果完全一致** |
| 并发 | 20 个线程抢 2 盏灯，恰好成功 2 单；30 个线程抢同一技师同一时段，恰好成功 1 单 |

只跑某一个测试：

```powershell
python -m unittest tests.test_booking.CreateBookingTests.test_every_moment_not_just_start_moment -v
```

---

## 11. 常见问题

**运行命令时提示 `No module named salon`**
你不在项目根目录。先 `cd` 到 `salon-booking`（里面有 `salon` 文件夹和 `README.md` 的那一层）再运行。

**提示 `python` 不是内部或外部命令**
没有安装 Python，或安装时没勾选添加到 PATH。重新安装并勾选 “Add Python to PATH”，或者把命令里的 `python` 换成 `py`。

**启动服务时提示端口被占用**
换一个端口，见 2.5 节的 `main(9000)` 写法。

**PowerShell 里 `curl` 报奇怪的参数错误**
PowerShell 里的 `curl` 是 `Invoke-WebRequest` 的别名，参数和真正的 curl 不同。请使用 `curl.exe`，或者用本文的 `Invoke-RestMethod` 写法。

**`Invoke-RestMethod` 遇到冲突直接报错，看不到原因**
这是 PowerShell 的行为：HTTP 状态码 4xx 会被当成异常。想看到完整的错误内容，用第 6 节第 5 步的 `curl.exe -i` 方式。

**重启服务后预约都没了**
正常。数据只存在内存里，重启就清空。

**查询的日期很远，结果全是可约，是 bug 吗？**
不是。这个版本没有限制日期范围，也没有区分节假日，每天都按 09:00–19:00 营业处理。

---

## 12. 局限与后续方向

当前版本是原型，以下内容没有做，也是后续可以扩展的方向：

- **持久化**：改用 PostgreSQL，设计见需求报告第 4 节（数据模型）和第 7 节（事务与幂等）。
- **登录与权限**：没有用户体系，没有顾客、技师、店长的角色区分，没有多商家隔离。
- **取消接口**：核心类有 `cancel_booking`，但 HTTP 服务没有暴露对应的路由。
- **技师技能和排班**：假设所有技师会做所有服务，没有休息时间。
- **服务之间的缓冲时间**：比如清洁设备的时间，目前没有。
- **时区**：全部按门店本地时间处理，没有真正的时区换算。
- **服务端的写入性能**：目前一把全局锁保护所有预约；单店场景足够，大规模下需要按设备类型拆分锁，或交给数据库事务。