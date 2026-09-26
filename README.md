# 生态缸造景设计会议 · 会议聊天后端

「生态缸造景设计会议」全栈应用的一个后端子集。上游项目里，设计师和客户在会议页面里聊方案，后端负责把每条消息落库、并通过 WebSocket 实时推给同一个会议里的所有人；此外还有素材库、案例库、水声降噪、Whisper 转写、发言者分离、AI 摘要和作品证书。本仓库只保留会议聊天这一组接口（HTTP 历史消息 + WebSocket 实时广播）和它共用的数据层，路径已从上游的 `backend/` 提到仓库根。素材、案例、音频、AI 摘要、证书模块都不在本仓库范围内。

## 目录

    database.py           SQLAlchemy engine / SessionLocal / get_db 依赖
    models.py             ORM 模型（用户、素材、案例、会议、消息、录音、摘要）
    schemas.py            Pydantic 请求与响应模型
    routers/chat.py       聊天接口，挂载前缀 /api/chat；内含 ConnectionManager 与 4 个路由

`routers/__init__.py` 是空文件，上游那个会把四个路由一次性 import 进来的 `main.py` 没有携带（它引用了裁剪范围之外的音频与 AI 模块）。测试里自己起一个 `FastAPI()`，把 `routers.chat.router` `include_router` 进去即可。

## 路由

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/chat/{meeting_id}/messages` | 会议历史消息，按 `timestamp` 升序；会议不存在返回 404「Meeting not found」 |
| POST | `/api/chat/message` | 落库一条消息，返回带 `sender` 的完整体；会议不存在返回 404「Meeting not found」 |
| DELETE | `/api/chat/message/{message_id}` | 删除一条消息；不存在返回 404「Message not found」 |
| WS | `/api/chat/ws/{meeting_id}` | 连上后进入收消息循环：每收到一条 JSON 就落库，再把落库结果广播给同一 `meeting_id` 的所有连接 |

## 广播出去的消息体（字段名与类型不要动）

    {
      "id": 12,
      "meeting_id": 3,
      "sender_id": 2,
      "content": "我想做一个60cm的生态缸",
      "message_type": "text",
      "timestamp": "2026-09-26T18:40:00.123456",
      "sender": {"id": 2, "name": "李先生", "role": "client", "avatar": null}
    }

`sender` 在库里查不到时是 `null`（不是省略这个键）。`timestamp` 是 ISO 字符串。WebSocket 客户端收到的一帧就是 `send_json` 出去的这个对象。

## 业务约定

- `ConnectionManager` 现在的行为：`active_connections` 是 `Dict[meeting_id, List[WebSocket]]`；`connect()` 先 `await websocket.accept()` 再按 `meeting_id` 入表；`disconnect()` 把连接从对应列表里摘掉，列表空了就把这个 key 删掉；`broadcast()` 遍历该 `meeting_id` 的列表，逐个 `await connection.send_json(message)`。模块级只有一个 `manager` 单例，所有会议共用它。
- 房间隔离：一个 `meeting_id` 就是一个房间，广播不得跨房间泄漏。这条现在成立，扩展之后也必须成立，并且要有测试钉住。
- 前端现在连 ws 时不带任何身份参数，服务端也不知道对面是谁。运维想知道「3 号会议现在几个人在线、都是谁」，只能去数数据库里的消息，很不准。
- 客户端断线重连之后，唯一能做的就是把 `GET /{meeting_id}/messages` 的全量历史重新拉一遍。会议聊到两三百条时，每次掉线都要重拉全量，前台会白屏一下；掉线期间别人发的消息也没有任何「你错过了哪几条」的口径。
- 某个客户端网络抽风、`send_json` 抛异常时，现在会发生什么，没有人测过，也没有人写下来。
- 历史消息接口那条「空库兜底」是坏的，而且不在本题范围内：库里一条消息都没有时，代码本来要返回两条写死的欢迎语，可这两条数据通不过 `MessageResponse` 校验（写死的 `sender` 缺 `created_at`），实际响应是 500。运维已经记了这一笔，另有排期。别顺手修，也别拿它当验收点；自己写测试时请绕开「会议存在、但一条消息都没有」这个组合。
- 404 文案（`Meeting not found` / `Message not found`）已被前端和运维脚本硬编码匹配，不要改。
- ws 循环里的异常处理现在是 `print(f"WebSocket error: {e}")`；扩展之后请走 logging，仓库里不要留 `print(`。
- `Message.timestamp` 由 ORM 默认值 `datetime.utcnow` 填，同一秒内落库的多条消息 timestamp 可能完全相同，按它排序不稳定。历史消息接口这个既有行为不要改；新增的顺序口径（如果有）另说，并写进 README。
- 补发这件事有两处存在两种合理做法、结论不同，需要你选：一是**补发游标由谁维护**（客户端每次自己带上「我收到哪儿了」，还是服务端按用户记住游标、重连时自动补），二是**请求的位置已经滑出缓冲窗口之后缺口怎么表达**（把还在窗口里的部分补给它并明确告知有缺口，还是直接回一个 4xx 让它回落到全量历史）。选定之后把选择和理由填进下面两个占位处，并让实现与之一致。

  > 选定方案（补发游标由谁维护）：（待填）

  > 选定方案（缓冲缺口怎么表达）：（待填）

## 运行与测试

依赖版本见 `requirements-task.txt`。运行环境使用预装好的共享虚拟环境，不要现场安装：

    ~/venvs/gsb-aqua/bin/python -m pytest tests/ -q

数据库默认 `sqlite:///./aquascape.db`，可用环境变量 `DATABASE_URL` 覆盖。测试请用 `tmp_path` 下的 sqlite 文件，通过 `app.dependency_overrides` 覆盖 `get_db`，自己 `create_all` 建表。

`ConnectionManager` 的语义建议直接用假连接对象驱动（鸭子类型就够：`async def accept()`、`async def send_json(data)`，需要模拟收消息时再加 `async def receive_text()`），比走真实 ws 传输稳，也好安排「第 N 次 send 抛异常」这种情形。`pytest-asyncio==0.24.0` 已装，默认是 strict 模式：异步用例要自己加 `@pytest.mark.asyncio`，或者在同步用例里用 `asyncio.run()` 驱动协程。

跑完整套测试之后仓库工作树应当保持干净，不留 `aquascape.db`，也不留别的产物。测试不得联网。
