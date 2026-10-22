"""
AI 服务层 — DeepSeek + 阿里云百炼 双引擎

提供：
1. chat() / chat_stream() — 通用 LLM 对话（兼容百炼/DeepSeek）
2. chat_with_functions() — Function Calling 对话（用于 Text-to-SQL）
"""

import json
import logging
import time
from datetime import datetime, date
from decimal import Decimal
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class AIJSONEncoder(json.JSONEncoder):
    """处理 Decimal/date/datetime 等数据库类型的 JSON 编码器"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


def _json_dumps(obj) -> str:
    """安全的 JSON 序列化，处理数据库类型"""
    return json.dumps(obj, ensure_ascii=False, cls=AIJSONEncoder)

# ── 全局客户端（懒加载） ──
_deepseek_client: OpenAI | None = None
_bailian_client: OpenAI | None = None


def _get_deepseek_client() -> OpenAI:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _deepseek_client


def _get_bailian_client() -> OpenAI:
    global _bailian_client
    if _bailian_client is None:
        _bailian_client = OpenAI(
            api_key=settings.bailian_api_key,
            base_url=settings.bailian_base_url,
        )
    return _bailian_client


# ── 通用对话 ──

def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
    enable_thinking: bool = False,
    provider: str = "bailian",
) -> str:
    """调用 LLM Chat Completions（非流式），返回回复文本。"""
    if provider == "deepseek":
        client = _get_deepseek_client()
        kwargs = dict(
            model=model or settings.deepseek_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.deepseek_temperature,
            max_tokens=max_tokens or settings.deepseek_max_tokens,
            stream=False,
        )
    else:
        client = _get_bailian_client()
        kwargs = dict(
            model=model or settings.bailian_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.bailian_temperature,
            max_tokens=max_tokens or settings.bailian_max_tokens,
            stream=False,
        )
        if enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": True}

    try:
        completion = client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM API 调用失败 ({provider}): {e}")
        raise


def chat_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    enable_thinking: bool = False,
    provider: str = "bailian",
):
    """调用 LLM Chat Completions（流式），返回生成器。"""
    if provider == "deepseek":
        client = _get_deepseek_client()
        kwargs = dict(
            model=model or settings.deepseek_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.deepseek_temperature,
            max_tokens=max_tokens or settings.deepseek_max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
    else:
        client = _get_bailian_client()
        kwargs = dict(
            model=model or settings.bailian_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.bailian_temperature,
            max_tokens=max_tokens or settings.bailian_max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        if enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": True}

    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                yield {
                    "content": delta.content or "",
                    "reasoning": getattr(delta, "reasoning_content", "") or "",
                }
            elif hasattr(chunk, "usage") and chunk.usage:
                yield {"usage": {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }}
    except Exception as e:
        logger.error(f"LLM 流式 API 调用失败 ({provider}): {e}")
        raise


# ── Function Calling（Text-to-SQL 核心） ──

SQL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": "执行 SQL 查询并返回结果。只能执行 SELECT 查询。返回列名和行数据。",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "要执行的 SQL SELECT 语句。使用 PostgreSQL 语法。例: SELECT s.name, sp.remain_hours FROM student s JOIN student_package sp ON s.id = sp.student_id WHERE s.status = '在读' LIMIT 10",
                },
                "reasoning": {
                    "type": "string",
                    "description": "解释为什么需要这个查询，你打算怎么分析数据",
                },
            },
            "required": ["sql", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def chat_with_functions(
    messages: list[dict],
    execute_sql_callback,
    model: str | None = None,
    max_tool_rounds: int = 5,
) -> dict:
    """
    Function Calling 对话 — 支持 LLM 调用 execute_sql 工具。
    非流式版本，返回最终回复。
    """
    client = _get_deepseek_client()
    start_time = time.time()
    tool_calls_log = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    kwargs = dict(
        model=model or settings.deepseek_model,
        messages=messages,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        tools=[SQL_TOOL_DEFINITION],
        tool_choice="auto",
        stream=False,
    )

    for _round in range(max_tool_rounds):
        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"DeepSeek Function Call 失败: {e}")
            raise

        message = completion.choices[0].message

        # 记录 token 用量
        if completion.usage:
            total_prompt_tokens += completion.usage.prompt_tokens or 0
            total_completion_tokens += completion.usage.completion_tokens or 0

        # 没有工具调用 → 返回最终回复
        if not message.tool_calls:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "content": message.content or "",
                "tool_calls": tool_calls_log,
                "latency_ms": latency_ms,
                "token_usage": {
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                },
            }

        # 处理工具调用
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            if func_name == "execute_sql":
                sql = func_args.get("sql", "")
                reasoning = func_args.get("reasoning", "")
                logger.info(f"🔍 LLM 请求执行 SQL:\n理由: {reasoning}\nSQL: {sql}")

                result = execute_sql_callback(sql)

                tool_calls_log.append({
                    "sql": sql,
                    "reasoning": reasoning,
                    "rows_returned": len(result.get("rows", [])),
                    "error": result.get("error"),
                })

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": func_name, "arguments": _json_dumps(func_args)},
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": _json_dumps(result),
                })
            else:
                logger.warning(f"未知工具调用: {func_name}")

    latency_ms = int((time.time() - start_time) * 1000)
    return {
        "content": message.content if message else "查询次数过多，请简化您的问题。",
        "tool_calls": tool_calls_log,
        "latency_ms": latency_ms,
        "token_usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
        },
    }


# ── 流式两阶段：先想后答 ──

def chat_stream_with_functions(
    messages: list[dict],
    execute_sql_callback,
    model: str | None = None,
    max_tool_rounds: int = 3,
):
    """
    流式 Function Calling — 两阶段：
    阶段1（非流式）：思考 → 生成 SQL → 执行 → 得到结果
    阶段2（流式）：基于结果生成自然语言回复

    每个 yield 返回事件 dict:
      {"type": "think", "content": "..."}
      {"type": "sql", "content": "SQL语句", "reasoning": "..."}
      {"type": "result", "error": "..."}  或 {"type": "result", "rows": N}
      {"type": "token", "content": "..."}
      {"type": "tokens", "prompt": N, "completion": N, "total": N}
    """
    client = _get_deepseek_client()
    total_prompt_tokens = 0
    total_completion_tokens = 0

    # ── 阶段1：思考 + 执行 SQL ──
    yield {"type": "think", "content": "正在分析您的问题..."}

    think_kwargs = dict(
        model=model or settings.deepseek_model,
        messages=messages,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        tools=[SQL_TOOL_DEFINITION],
        tool_choice="auto",
        stream=False,
    )

    sql_executed = False
    sql_result_data = None

    for _round in range(max_tool_rounds):
        try:
            completion = client.chat.completions.create(**think_kwargs)
        except Exception as e:
            logger.error(f"DeepSeek 思考阶段失败: {e}")
            yield {"type": "error", "content": f"AI 服务调用失败: {str(e)}"}
            return

        message = completion.choices[0].message

        if completion.usage:
            total_prompt_tokens += completion.usage.prompt_tokens or 0
            total_completion_tokens += completion.usage.completion_tokens or 0

        # 没有工具调用 → 思考完成
        if not message.tool_calls:
            # 如果没有执行任何 SQL，直接用回复内容（简单问候类）
            if not sql_executed and message.content:
                # 直接进入阶段2 流式输出
                pass
            break

        # 处理工具调用
        for tool_call in message.tool_calls:
            if tool_call.function.name != "execute_sql":
                continue
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                continue

            sql = func_args.get("sql", "")
            reasoning = func_args.get("reasoning", "")

            if not sql:
                continue

            yield {"type": "sql", "content": sql, "reasoning": reasoning}

            # 执行 SQL
            result = execute_sql_callback(sql)
            sql_executed = True
            sql_result_data = result

            if result.get("error"):
                yield {"type": "result", "error": result["error"]}
            else:
                yield {"type": "result", "rows": len(result.get("rows", []))}

            # 注入结果回对话
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": "execute_sql", "arguments": _json_dumps(func_args)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": _json_dumps(result),
            })

    # ── 阶段2：流式生成最终回复 ──
    yield {"type": "think", "content": "正在生成回答..."}

    # 如果执行了 SQL，用助理消息 + tool 消息作为上下文再生成回复
    # 如果没有执行 SQL（简单问候），直接用原文
    stream_messages = messages
    if not sql_executed and message and message.content:
        # 简单问候直接流式输出
        stream_messages = messages + [{"role": "assistant", "content": message.content}]
        for char in message.content:
            yield {"type": "token", "content": char}
        # 没有 token 用量追加，直接返回
        return

    # 用流式生成回复
    stream_kwargs = dict(
        model=model or settings.deepseek_model,
        messages=stream_messages,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )

    try:
        stream = client.chat.completions.create(**stream_kwargs)
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield {"type": "token", "content": delta.content}
            elif hasattr(chunk, "usage") and chunk.usage:
                if chunk.usage.prompt_tokens:
                    total_prompt_tokens += chunk.usage.prompt_tokens
                if chunk.usage.completion_tokens:
                    total_completion_tokens += chunk.usage.completion_tokens
    except Exception as e:
        logger.error(f"DeepSeek 流式回复失败: {e}")
        yield {"type": "error", "content": f"生成回复失败: {str(e)}"}
        return

    # 返回 token 用量
    yield {
        "type": "tokens",
        "prompt": total_prompt_tokens,
        "completion": total_completion_tokens,
        "total": total_prompt_tokens + total_completion_tokens,
    }
