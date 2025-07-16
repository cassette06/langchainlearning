# 这个文件就是服务器程序
import asyncio

from agent import QueueCallbackHandler, agent_executor
from fastapi import FastAPI
from fastapi.responses import StreamingResponse 
# 专门用于流式响应的类
# 可以实时传输数据，不需要等待全部数据生成完成
from fastapi.middleware.cors import CORSMiddleware

# initilizing our application
app = FastAPI() # 创建应用实例，这就是服务器
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# streaming function
async def token_generator(content: str, streamer: QueueCallbackHandler):
    task = asyncio.create_task(agent_executor.invoke(
        input=content,
        streamer=streamer,
        verbose=True  # set to True to see verbose output in console
    ))
    # initialize various components to stream
    async for token in streamer:
        try:
            if token == "<<STEP_END>>":
                # send end of step token
                yield "</step>" #这一步yield直接发送给客户端
            elif token == "<<DONE>>":
                # send final completion token
                yield "</step>"
                break
            elif tool_calls := token.message.additional_kwargs.get("tool_calls"):
                if tool_name := tool_calls[0]["function"]["name"]:
                    # send start of step token followed by step name tokens
                    yield f"<step><step_name>{tool_name}</step_name>"
                if tool_args := tool_calls[0]["function"]["arguments"]:
                    # tool args are streamed directly, ensure it's properly encoded
                    yield tool_args 
        except Exception as e:
            print(f"Error streaming token: {e}")
            continue
    await task

# invoke function
@app.post("/invoke") # 装饰器：注册路由
async def invoke(content: str):
    queue: asyncio.Queue = asyncio.Queue()
    streamer = QueueCallbackHandler(queue)
    # return the streaming response
    return StreamingResponse(
        token_generator(content, streamer), # 异步生成器
        media_type="text/event-stream",
        # 浏览器会这样理解：
        # "这是一个事件流，数据会持续到达，不要等待全部完成"
        headers={
            "Cache-Control": "no-cache",
            # 作用：禁止缓存
            # 原因：流式数据是实时的，不能被缓存
            # 效果：每次请求都是新的数据

            # 如果有缓存：
            # 第一次请求：客户端看到实时数据
            # 第二次请求：客户端看到缓存的旧数据（错误！）

            # 禁止缓存：
            # 每次请求：客户端都看到最新的实时数据（正确！）
            "Connection": "keep-alive",
            # 作用：保持连接
            # 原因：流式传输需要长连接
            # 效果：一次连接，多次数据传输

            # 普通HTTP：
            # 1. 建立连接
            # 2. 发送请求
            # 3. 接收响应
            # 4. 关闭连接

            # 流式HTTP：
            # 1. 建立连接
            # 2. 发送请求
            # 3. 接收数据流...  ← 连接保持打开
            # 4. 接收数据流...
            # 5. 接收数据流...
            # 6. 数据结束，关闭连接
        }
    )
