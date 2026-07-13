from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import sqlparse
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from openai import OpenAI
from openai import APIError as OpenAIAPIError
from openai import APITimeoutError, BadRequestError
from pydantic import BaseModel, Field
from wren.config import WrenConfig, load_config
from wren.engine import WrenEngine
from wren.memory.markdown import load_query_pairs
from wren.memory.store import MemoryStore
from wren.model.data_source import DataSource


LOGGER = logging.getLogger("ask_service")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
ENV_FILE = SERVICE_DIR / ".env"
load_dotenv(ENV_FILE)


class ErrorInfo(BaseModel):
    code: str
    message: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户自然语言问题")
    allowed_regions: list[str] = Field(default_factory=list)
    recall_limit: int | None = None
    fetch_limit: int | None = None


class AskResponse(BaseModel):
    ok: bool
    trace_id: str
    need_clarification: bool
    clarification_question: str = ""
    question: str
    sql: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    chart: dict[str, Any] = Field(
        default_factory=lambda: {"type": "table", "xField": "", "yField": ""}
    )
    latency_ms: int
    error: ErrorInfo | None = None


class AskRuntime:
    def __init__(self) -> None:
        self.vllm_base_url = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
        self.vllm_api_key = os.getenv("VLLM_API_KEY", "dummy")
        self.vllm_model = os.getenv("VLLM_MODEL", "qwen2.5-7b-instruct")

        self.project_path = self._resolve_path(os.environ["WREN_PROJECT_PATH"])
        self.mdl_path = self._resolve_path(os.environ["WREN_MDL_PATH"])
        self.conn_file = self._resolve_path(os.environ["WREN_CONN_FILE"])
        self.memory_path = self._resolve_path(os.environ["WREN_MEMORY_PATH"])

        self.strict_mode = os.getenv("WREN_STRICT_MODE", "true").lower() == "true"
        self.query_timeout_sec = int(os.getenv("QUERY_TIMEOUT_SEC", "90"))
        self.max_result_rows = int(os.getenv("MAX_RESULT_ROWS", "200"))
        self.default_recall_limit = int(os.getenv("DEFAULT_RECALL_LIMIT", "3"))
        self.default_fetch_limit = int(os.getenv("DEFAULT_FETCH_LIMIT", "6"))

        self.memory_store: MemoryStore | None = None
        self.llm_client: OpenAI | None = None
        self.conn_dict: dict[str, Any] = {}
        self.data_source: DataSource | None = None
        self.config = WrenConfig(strict_mode=self.strict_mode)
        self._manifest_dict: dict[str, Any] | None = None
        self._manifest_b64: str | None = None
        self._manifest_mtime_ns: int | None = None

    def startup(self) -> None:
        startup_started = time.perf_counter()
        log_event(
            "startup_begin",
            project_root=str(PROJECT_ROOT),
            env_file=str(ENV_FILE),
        )
        if not self.project_path.exists():
            raise RuntimeError(f"Wren 项目目录不存在: {self.project_path}")
        if not self.mdl_path.exists():
            raise RuntimeError(f"MDL 文件不存在: {self.mdl_path}")
        if not self.conn_file.exists():
            raise RuntimeError(f"连接配置不存在: {self.conn_file}")

        conn_started = time.perf_counter()
        self.conn_dict = self._load_connection_info(self.conn_file)
        datasource = self.conn_dict.get("datasource")
        if not datasource:
            raise RuntimeError("connection_info.json 缺少 datasource")
        self.data_source = DataSource(str(datasource).lower())
        log_event(
            "startup_connection_loaded",
            datasource=str(datasource),
            conn_file=str(self.conn_file),
            elapsed_ms=int((time.perf_counter() - conn_started) * 1000),
        )

        memory_started = time.perf_counter()
        self.memory_store = MemoryStore(path=self.memory_path)
        log_event(
            "startup_memory_ready",
            memory_path=str(self.memory_path),
            elapsed_ms=int((time.perf_counter() - memory_started) * 1000),
        )

        llm_started = time.perf_counter()
        self.llm_client = OpenAI(
            base_url=self.vllm_base_url,
            api_key=self.vllm_api_key,
        )
        log_event(
            "startup_llm_client_ready",
            vllm_base_url=self.vllm_base_url,
            vllm_model=self.vllm_model,
            elapsed_ms=int((time.perf_counter() - llm_started) * 1000),
        )

        manifest_started = time.perf_counter()
        self._load_manifest(force=True)
        log_event(
            "startup_manifest_loaded",
            mdl_path=str(self.mdl_path),
            elapsed_ms=int((time.perf_counter() - manifest_started) * 1000),
        )

        wren_home = Path(os.environ.get("WREN_HOME", str(Path.home() / ".wren"))).expanduser()
        try:
            loaded = load_config(wren_home)
            self.config = WrenConfig(
                strict_mode=self.strict_mode or loaded.strict_mode,
                denied_functions=loaded.denied_functions,
                allowed_source_functions=loaded.allowed_source_functions,
            )
        except Exception as exc:
            LOGGER.warning("加载 Wren 配置失败，使用服务内默认配置: %s", exc)
            self.config = WrenConfig(strict_mode=self.strict_mode)

        log_event(
            "startup_completed",
            project_path=str(self.project_path),
            model=self.vllm_model,
            strict_mode=self.config.strict_mode,
            elapsed_ms=int((time.perf_counter() - startup_started) * 1000),
        )

    def shutdown(self) -> None:
        log_event("shutdown_begin")
        self.memory_store = None
        self.llm_client = None
        log_event("shutdown_completed")

    def status(self) -> dict[str, Any]:
        return {
            "project_path": str(self.project_path),
            "mdl_path": str(self.mdl_path),
            "conn_file": str(self.conn_file),
            "memory_path": str(self.memory_path),
            "vllm_base_url": self.vllm_base_url,
            "vllm_model": self.vllm_model,
            "strict_mode": self.config.strict_mode,
            "memory_tables": self.memory_store.status() if self.memory_store else {},
        }

    def _load_manifest(self, *, force: bool = False) -> tuple[dict[str, Any], str]:
        current_mtime = self.mdl_path.stat().st_mtime_ns
        if (
            not force
            and self._manifest_dict is not None
            and self._manifest_b64 is not None
            and self._manifest_mtime_ns == current_mtime
        ):
            return self._manifest_dict, self._manifest_b64

        content = self.mdl_path.read_bytes()
        self._manifest_dict = json.loads(content.decode("utf-8"))
        self._manifest_b64 = base64.b64encode(content).decode("utf-8")
        self._manifest_mtime_ns = current_mtime
        return self._manifest_dict, self._manifest_b64

    def current_manifest(self) -> tuple[dict[str, Any], str]:
        return self._load_manifest()

    def reindex(self) -> dict[str, Any]:
        manifest, _ = self._load_manifest(force=True)
        assert self.memory_store is not None
        schema_result = self.memory_store.index_schema(manifest, seed_queries=True)
        md_pairs = load_query_pairs(self.project_path)
        query_result = self.memory_store.load_queries(md_pairs, upsert=True) if md_pairs else {}
        return {
            "schema_result": schema_result,
            "query_result": query_result,
        }

    def build_engine(self) -> WrenEngine:
        _, manifest_b64 = self.current_manifest()
        assert self.data_source is not None
        return WrenEngine(
            manifest_str=manifest_b64,
            data_source=self.data_source,
            connection_info=self.conn_dict,
            config=self.config,
        )

    @staticmethod
    def _normalize_conn(conn: dict[str, Any]) -> dict[str, Any]:
        if "properties" in conn and isinstance(conn["properties"], dict):
            props = dict(conn["properties"])
            props["datasource"] = conn.get("datasource", props.get("datasource"))
            return props
        return conn

    def _load_connection_info(self, path: Path) -> dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError(f"连接配置必须是 JSON Object: {path}")
        return self._normalize_conn(raw)

    @staticmethod
    def _resolve_path(value: str) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()


runtime = AskRuntime()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def shorten_text(value: str, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}..."


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    LOGGER.info(json_dumps(payload))


def make_response(
    *,
    ok: bool,
    trace_id: str,
    question: str,
    latency_ms: int,
    need_clarification: bool = False,
    clarification_question: str = "",
    sql: str = "",
    rows: list[dict[str, Any]] | None = None,
    summary: str = "",
    chart: dict[str, Any] | None = None,
    error: ErrorInfo | None = None,
) -> AskResponse:
    return AskResponse(
        ok=ok,
        trace_id=trace_id,
        need_clarification=need_clarification,
        clarification_question=clarification_question,
        question=question,
        sql=sql,
        rows=rows or [],
        summary=summary,
        chart=chart or {"type": "table", "xField": "", "yField": ""},
        latency_ms=latency_ms,
        error=error,
    )


def strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_balanced_json(text: str) -> str | None:
    start = None
    depth = 0
    in_string = False
    escape = False

    for idx, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = idx
                depth = 1
                in_string = False
                escape = False
            continue

        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def cleanup_json_text(text: str) -> str:
    cleaned = strip_code_fences(text)
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    cleaned = re.sub(r"\bTrue\b", "true", cleaned)
    cleaned = re.sub(r"\bFalse\b", "false", cleaned)
    cleaned = re.sub(r"\bNone\b", "null", cleaned)
    return cleaned.strip()


def parse_json_candidate(text: str) -> dict[str, Any] | None:
    candidates = []
    cleaned = cleanup_json_text(text)
    if cleaned:
        candidates.append(cleaned)
    extracted = extract_balanced_json(cleaned)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def looks_like_sql(text: str) -> bool:
    return bool(re.match(r"^\s*(select|with)\b", text, re.IGNORECASE))


def ensure_safe_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    if not sql:
        raise ValueError("LLM 没有返回可执行 SQL")

    lowered = f" {sql.lower()} "
    forbidden = [
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " truncate ",
        " alter ",
        " create ",
        " grant ",
        " revoke ",
        " replace ",
    ]
    if any(token in lowered for token in forbidden):
        raise ValueError("仅允许只读 SELECT/WITH 查询")

    statements = [part.strip() for part in sqlparse.split(sql) if part.strip()]
    if len(statements) != 1:
        raise ValueError("仅允许单条 SQL")

    first = statements[0].split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        raise ValueError("仅允许 SELECT/WITH 查询")
    return statements[0]


def normalize_chart(chart: Any) -> dict[str, Any]:
    default = {"type": "table", "xField": "", "yField": ""}
    if not isinstance(chart, dict):
        return default
    return {
        "type": str(chart.get("type", default["type"])),
        "xField": str(chart.get("xField", default["xField"])),
        "yField": str(chart.get("yField", default["yField"])),
    }


def llm_chat(messages: list[dict[str, str]], *, temperature: float = 0.1) -> str:
    assert runtime.llm_client is not None
    response = runtime.llm_client.chat.completions.create(
        model=runtime.vllm_model,
        temperature=temperature,
        messages=messages,
    )
    return (response.choices[0].message.content or "").strip()


def repair_json_with_llm(raw_text: str) -> dict[str, Any] | None:
    repaired = llm_chat(
        [
            {
                "role": "system",
                "content": (
                    "你是 JSON 修复助手。请把用户给出的内容整理为一个合法 JSON 对象。"
                    "只能输出 JSON，不要解释。"
                ),
            },
            {"role": "user", "content": raw_text},
        ],
        temperature=0.0,
    )
    return parse_json_candidate(repaired)


def parse_plan_response(raw_text: str) -> dict[str, Any]:
    parsed = parse_json_candidate(raw_text)
    if parsed is not None:
        return parsed

    cleaned = strip_code_fences(raw_text)
    if looks_like_sql(cleaned):
        return {
            "need_clarification": False,
            "clarification_question": "",
            "sql": cleaned,
            "chart": {"type": "table", "xField": "", "yField": ""},
        }

    repaired = repair_json_with_llm(cleaned)
    if repaired is not None:
        return repaired

    raise ValueError("LLM 返回内容不是有效 JSON，也无法修复")


def build_plan_prompt(
    *,
    question: str,
    recalls: list[dict[str, Any]],
    fetched: dict[str, Any],
    allowed_regions: list[str],
) -> str:
    return f"""
你是一个基于 Wren 语义层的 BI 问数助手。
你必须输出 JSON 对象，不允许输出 markdown，不允许输出解释。

规则：
1. 只允许生成 SELECT/WITH 查询。
2. 只能使用 Wren 已建模对象和字段。
3. 如果问题缺少关键条件，返回 need_clarification=true。
4. 如果 allowed_regions 非空，你必须把地区限制在这些值内。
5. 默认返回表格，chart.type 用 table/bar/line 之一。

输出格式：
{{
  "need_clarification": false,
  "clarification_question": "",
  "sql": "",
  "chart": {{
    "type": "table",
    "xField": "",
    "yField": ""
  }}
}}

用户问题：
{question}

相似问法召回：
{json_dumps(recalls)}

语义上下文：
{json_dumps(fetched)}

allowed_regions：
{json_dumps(allowed_regions)}
""".strip()


def build_summary_prompt(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    return f"""
你是中文数据分析助手。
请根据用户问题、SQL 和结果，生成简洁准确的中文结论。
如果结果为空，请明确回复“未查询到符合条件的数据”。
不要编造没有出现在结果中的数值。

用户问题：
{question}

SQL：
{sql}

查询结果：
{json_dumps(rows)}
""".strip()


def llm_plan(
    *,
    question: str,
    recalls: list[dict[str, Any]],
    fetched: dict[str, Any],
    allowed_regions: list[str],
) -> dict[str, Any]:
    raw_text = llm_chat(
        [
            {
                "role": "system",
                "content": "你是严谨的数据分析助手，必须只输出 JSON 对象。",
            },
            {
                "role": "user",
                "content": build_plan_prompt(
                    question=question,
                    recalls=recalls,
                    fetched=fetched,
                    allowed_regions=allowed_regions,
                ),
            },
        ],
        temperature=0.1,
    )
    return parse_plan_response(raw_text)


def llm_summary(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    return llm_chat(
        [
            {
                "role": "system",
                "content": "你是中文数据分析助手，请输出简洁、可信的业务结论。",
            },
            {
                "role": "user",
                "content": build_summary_prompt(question, sql, rows),
            },
        ],
        temperature=0.2,
    )


def execute_sql(sql: str) -> list[dict[str, Any]]:
    started = time.perf_counter()
    with runtime.build_engine() as engine:
        table = engine.query(sql, limit=runtime.max_result_rows)
    rows = table.to_pylist()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log_event(
        "sql_query_finished",
        sql_preview=shorten_text(sql, 200),
        row_count=len(rows),
        elapsed_ms=elapsed_ms,
    )
    return rows


def dry_run_sql(sql: str) -> None:
    started = time.perf_counter()
    with runtime.build_engine() as engine:
        engine.dry_run(sql)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log_event(
        "sql_dry_run_finished",
        sql_preview=shorten_text(sql, 200),
        elapsed_ms=elapsed_ms,
    )


def classify_exception(exc: Exception) -> ErrorInfo:
    if isinstance(exc, ValueError):
        return ErrorInfo(code="BAD_PLAN", message=str(exc))
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return ErrorInfo(code="LLM_TIMEOUT", message="大模型响应超时")
    if isinstance(exc, BadRequestError):
        return ErrorInfo(code="LLM_BAD_REQUEST", message=str(exc))
    if isinstance(exc, OpenAIAPIError):
        return ErrorInfo(code="LLM_API_ERROR", message=str(exc))
    return ErrorInfo(code="INTERNAL_ERROR", message=str(exc))


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime.startup()
    yield
    runtime.shutdown()


app = FastAPI(title="ask_service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "ask_service",
        "project_path": str(runtime.project_path),
        "mdl_path": str(runtime.mdl_path),
        "memory_path": str(runtime.memory_path),
        "vllm_base_url": runtime.vllm_base_url,
        "vllm_model": runtime.vllm_model,
        "strict_mode": runtime.config.strict_mode,
    }


@app.get("/status")
def status() -> dict[str, Any]:
    return runtime.status()


@app.post("/admin/reindex")
def reindex() -> dict[str, Any]:
    return {
        "ok": True,
        **runtime.reindex(),
    }


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    trace_id = uuid.uuid4().hex[:16]
    start = time.time()

    try:
        if not req.question.strip():
            raise ValueError("问题不能为空")

        log_event(
            "ask_request_received",
            trace_id=trace_id,
            question=shorten_text(req.question),
            allowed_regions=req.allowed_regions,
            recall_limit=req.recall_limit or runtime.default_recall_limit,
            fetch_limit=req.fetch_limit or runtime.default_fetch_limit,
        )

        assert runtime.memory_store is not None
        recall_started = time.perf_counter()
        manifest, _ = runtime.current_manifest()

        recalls = runtime.memory_store.recall_queries(
            req.question,
            limit=req.recall_limit or runtime.default_recall_limit,
        )
        fetched = runtime.memory_store.get_context(
            manifest,
            req.question,
            limit=req.fetch_limit or runtime.default_fetch_limit,
            threshold=30000,
        )
        recall_elapsed_ms = int((time.perf_counter() - recall_started) * 1000)
        log_event(
            "ask_context_ready",
            trace_id=trace_id,
            recall_count=len(recalls),
            fetch_strategy=fetched.get("strategy"),
            fetch_result_count=len(fetched.get("results", [])) if isinstance(fetched, dict) else 0,
            elapsed_ms=recall_elapsed_ms,
        )

        plan_started = time.perf_counter()
        plan = llm_plan(
            question=req.question,
            recalls=recalls,
            fetched=fetched,
            allowed_regions=req.allowed_regions,
        )
        log_event(
            "ask_plan_ready",
            trace_id=trace_id,
            need_clarification=bool(plan.get("need_clarification")),
            has_sql=bool(str(plan.get("sql", "")).strip()),
            elapsed_ms=int((time.perf_counter() - plan_started) * 1000),
        )

        if bool(plan.get("need_clarification")):
            latency_ms = int((time.time() - start) * 1000)
            log_event(
                "ask_need_clarification",
                trace_id=trace_id,
                latency_ms=latency_ms,
                clarification_question=shorten_text(
                    str(plan.get("clarification_question", "请补充更具体的查询条件"))
                ),
            )
            return make_response(
                ok=True,
                trace_id=trace_id,
                question=req.question,
                need_clarification=True,
                clarification_question=str(
                    plan.get("clarification_question", "请补充更具体的查询条件")
                ),
                latency_ms=latency_ms,
                summary="需要补充查询条件后才能继续问数。",
                chart=normalize_chart(plan.get("chart")),
            )

        sql = ensure_safe_sql(str(plan.get("sql", "")))
        dry_run_sql(sql)
        rows = execute_sql(sql)
        summary_started = time.perf_counter()
        summary = llm_summary(req.question, sql, rows)
        summary_elapsed_ms = int((time.perf_counter() - summary_started) * 1000)

        latency_ms = int((time.time() - start) * 1000)
        response = make_response(
            ok=True,
            trace_id=trace_id,
            question=req.question,
            sql=sql,
            rows=rows,
            summary=summary,
            chart=normalize_chart(plan.get("chart")),
            latency_ms=latency_ms,
        )
        log_event(
            "ask_request_completed",
            trace_id=trace_id,
            latency_ms=latency_ms,
            row_count=len(rows),
            summary_elapsed_ms=summary_elapsed_ms,
            sql_preview=shorten_text(sql, 200),
        )
        return response
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.time() - start) * 1000)
        error = classify_exception(exc)
        LOGGER.exception("trace_id=%s ask failed", trace_id)
        log_event(
            "ask_request_failed",
            trace_id=trace_id,
            latency_ms=latency_ms,
            error_code=error.code,
            error_message=error.message,
        )
        response = make_response(
            ok=False,
            trace_id=trace_id,
            question=req.question,
            latency_ms=latency_ms,
            summary="当前问数服务暂时不可用，请稍后重试，或换一种更明确的问法。",
            error=error,
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(response))
