# 生态缸造景设计会议 · 会议聊天后端

「生态缸造景设计会议」全栈应用的一个后端子集。上游项目里，设计师和客户在会议页面里聊方案，后端负责把每条消息落库、并通过 WebSocket 实时推给同一个会议里的所有人；此外还有素材库、案例库、水声降噪、Whisper 转写、发言者分离、AI 摘要和作品证书。本仓库只保留会议聊天这一组接口（HTTP 历史消息 + WebSocket 实时广播）和它共用的数据层，路径已从上游的 `backend/` 提到仓库根。素材、案例、音频、AI 摘要、证书模块都不在本仓库范围内。

## 目录

    database.py           SQLAlchemy engine / SessionLocal / get_db 依赖
    models.py             ORM 模型（用户、素材、案例、会议、消息、录音、摘要）
    schemas.py            Pydantic 请求与响应模型
    routers/chat.py       聊天接口，挂载前缀 /api/chat；内含 ConnectionManager 与 4 个路由
    tests/                pytest 测试（presence / 序号 / 广播隔离 / 补发 / 既有行为）

`routers/__init__.py` 是空文件，上游那个会把四个路由一次性 import 进来的 `main.py` 没有携带（它引用了裁剪范围之外的音频与 AI 模块）。测试里自己起一个 `FastAPI()`，把 `routers.chat.router` `include_router` 进去即可。

## 路由

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/{meeting_id}/messages` | 会议历史消息，按 `timestamp` 升序；会议不存在返回 404「Meeting not found」 |
| POST | `/api/chat/message` | 落库一条消息，返回带 `sender` 的完整体；会议不存在返回 404「Meeting not found」 |
| DELETE | `/api/chat/message/{message_id}` | 删除一条消息；不存在返回 404「Message not found」 |
| GET | `/api/chat/{meeting_id}/presence` | 在线名单：当前连接数、可识别身份的在线用户、匿名连接数；会议不存在返回 404「Meeting not found」 |
| GET | `/api/chat/{meeting_id}/replay?after_seq=K` | 掉线补发：返回序号大于 `K` 的缓冲消息（`after_seq` 缺省为 0）；会议不存在返回 404「Meeting not found」 |
| WS | `/api/chat/ws/{meeting_id}` | 连上后进入收消息循环：每收到一条 JSON 就落库，再把落库结果广播给同一 `meeting_id` 的所有连接。可选查询参数 `user_id` 自报身份 |

## 在线名单（presence）

`GET /api/chat/{meeting_id}/presence` 的响应：

    {
      "meeting_id": 3,
      "connection_count": 3,
      "online_users": [2, 7],
      "anonymous_count": 1
    }

- `connection_count`：这个房间当前的连接总数（含匿名）。
- `online_users`：能识别出身份的在线用户 id，去重后升序。身份来自 ws 连接时客户端自报的 `user_id` 查询参数（例如 `/api/chat/ws/3?user_id=7`）。**身份是客户端自报的，服务端不做任何校验**；不带 `user_id`（或值不是整数）也能正常连接、正常聊天，只是计入匿名。
- `anonymous_count`：认不出身份的连接数。
- 连接断开的瞬间就从名单里摘掉，不留僵尸。

## 消息序号（seq）

- 广播出去的那一帧，在既有七个字段之外多带一个 `seq` 字段（整数）。
- 序号由 `ConnectionManager` 在**每次广播时**分配：该房间的计数器加一，写进这一帧。
- 每个房间（`meeting_id`）各自从 1 起单调递增，同一进程内只增不减，房间之间互不串号。
- 房间清空（所有连接断开）之后计数器不重置，下次有人进来广播时序号延续。
- 序号是进程内存状态，进程重启后从 1 重新计；`POST /api/chat/message` 只落库不广播，不产生序号。

## 掉线补发（replay）

- 每个房间在服务端内存里保留最近 N 条广播帧的缓冲，N 由环境变量 `CHAT_REPLAY_BUFFER_SIZE` 配置，默认 50；超出就把最老的挤掉。
- `GET /api/chat/{meeting_id}/replay?after_seq=K` 的响应：

      {
        "meeting_id": 3,
        "messages": [ ... 序号大于 K 的广播帧，按 seq 升序，同一 seq 不重复 ... ],
        "gap": false,
        "latest_seq": 87
      }

- `messages` 里每一帧就是广播帧的完整形态（七个既有字段加 `seq`）。
- `gap` 为 `true` 表示请求的位置已经滑出缓冲窗口（`after_seq` 之前、窗口之外还有消息被挤掉了），客户端应回落到 `GET /{meeting_id}/messages` 全量历史。
- `latest_seq` 是这个房间当前已分配的最大序号，客户端可以拿它更新自己的游标。

## 广播出去的消息体（字段名与类型不要动）

    {
      "id": 12,
      "meeting_id": 3,
      "sender_id": 2,
      "content": "我想做一个60cm的生态缸",
      "message_type": "text",
      "timestamp": "2026-09-26T18:40:00.123456",
      "sender": {"id": 2, "name": "李先生", "role": "client", "avatar": null},
      "seq": 87
    }

`sender` 在库里查不到时是 `null`（不是省略这个键）。`timestamp` 是 ISO 字符串。WebSocket 客户端收到的一帧就是 `send_json` 出去的这个对象。

## 业务约定

- `ConnectionManager` 的行为：`active_connections` 是 `Dict[meeting_id, List[WebSocket]]`；`connect()` 先 `await websocket.accept()` 再按 `meeting_id` 入表，如果调用方带了 `user_id` 就顺手记进 `connection_identities`；`disconnect()` 把连接从对应列表和身份表里同时摘掉，列表空了就把这个 key 删掉。`broadcast()` 先给消息分配本房间的 `seq`、把这一帧存入本房间的补发缓冲，然后**在连接列表的快照上**逐个 `await connection.send_json(frame)`——广播途中有人断开不会改到正在遍历的列表。单个连接的 `send_json` 抛异常时，这个连接被移出名单、后续广播不再发给它，同房间其余连接照常收到，`broadcast` 本身不向调用方抛异常。模块级只有一个 `manager` 单例，所有会议共用它。
- 房间隔离：一个 `meeting_id` 就是一个房间，广播不得跨房间泄漏。这条现在成立，扩展之后也必须成立，并且要有测试钉住。
- 在线身份：前端连 ws 时可以带 `?user_id=` 查询参数自报身份，服务端不校验；不带也能正常连接和聊天（计入匿名）。运维查「3 号会议现在几个人在线、都是谁」走 `GET /api/chat/3/presence`。
- 掉线补发：客户端断线重连之后，带自己最后收到的 `seq` 调 `GET /{meeting_id}/replay?after_seq=K` 补齐缺口；`gap=true` 说明缺口已经滑出缓冲窗口，回落到全量历史。
- 某个客户端网络抽风、`send_json` 抛异常时：这一帧其余连接照常收到，坏连接被清出名单且后续广播不再发给它，`broadcast` 不向上抛异常。有测试钉住。
- 历史消息接口那条「空库兜底」是坏的，而且不在本题范围内：库里一条消息都没有时，代码本来要返回两条写死的欢迎语，可这两条数据通不过 `MessageResponse` 校验（写死的 `sender` 缺 `created_at`），实际响应是 500。运维已经记了这一笔，另有排期。别顺手修，也别拿它当验收点；自己写测试时请绕开「会议存在、但一条消息都没有」这个组合。
- 404 文案（`Meeting not found` / `Message not found`）已被前端和运维脚本硬编码匹配，不要改。
- ws 循环里的异常处理走 logging（`logger.exception`），仓库里不再保留 print 调用。
- `Message.timestamp` 由 ORM 默认值 `datetime.utcnow` 填，同一秒内落库的多条消息 timestamp 可能完全相同，按它排序不稳定。历史消息接口这个既有行为不要改；新增的顺序口径（如果有）另说，并写进 README。
- 补发这件事有两处存在两种合理做法、结论不同，需要你选：一是**补发游标由谁维护**（客户端每次自己带上「我收到哪儿了」，还是服务端按用户记住游标、重连时自动补），二是**请求的位置已经滑出缓冲窗口之后缺口怎么表达**（把还在窗口里的部分补给它并明确告知有缺口，还是直接回一个 4xx 让它回落到全量历史）。选定之后把选择和理由填进下面两个占位处，并让实现与之一致。

  > 选定方案（补发游标由谁维护）：**客户端维护**。客户端每次请求自己带上 `after_seq`（我收到哪儿了）。理由：身份本来就是客户端自报、服务端不校验的，服务端没有可靠锚点按用户记游标；无状态重放让换设备、多标签页、进程重启都自然工作，服务端也不必为游标引入额外存储。

  > 选定方案（缓冲缺口怎么表达）：**把还在窗口里的部分补给它，并用 `gap: true` 明确告知有缺口**（响应里同时带 `latest_seq` 方便更新游标）。理由：客户端能先拿到窗口内还活着的消息、减少白屏；是否回落全量历史由前端按场景决定，比直接回 4xx 更柔性，响应也保持 200 语义一致。

## 运行与测试

依赖版本见 `requirements-task.txt`。运行环境使用预装好的共享虚拟环境，不要现场安装：

    ~/venvs/gsb-aqua/bin/python -m pytest tests/ -q

数据库默认 `sqlite:///./aquascape.db`，可用环境变量 `DATABASE_URL` 覆盖。测试请用 `tmp_path` 下的 sqlite 文件，通过 `app.dependency_overrides` 覆盖 `get_db`，自己 `create_all` 建表。

`ConnectionManager` 的语义建议直接用假连接对象驱动（鸭子类型就够：`async def accept()`、`async def send_json(data)`，需要模拟收消息时再加 `async def receive_text()`），比走真实 ws 传输稳，也好安排「第 N 次 send 抛异常」这种情形。`pytest-asyncio==0.24.0` 已装，默认是 strict 模式：异步用例要自己加 `@pytest.mark.asyncio`，或者在同步用例里用 `asyncio.run()` 驱动协程。

跑完整套测试之后仓库工作树应当保持干净，不留 `aquascape.db`，也不留别的产物。测试不得联网。
