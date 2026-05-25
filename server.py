import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple

APP_NAME = "Requirements Extractor"
TOOL_NAME = "extract_requirements"
SUPPORT_EMAIL = "sidcraigau@gmail.com"

OUTPUT_FIELDS = {
    "functional_requirements",
    "constraints",
    "acceptance_criteria",
    "missing_fields",
    "source_text",
    "errors",
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "functional_requirements": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "source_text": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": ["missing_field", "invalid_value", "out_of_scope", "internal_error"],
                    },
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "functional_requirements",
        "constraints",
        "acceptance_criteria",
        "missing_fields",
        "source_text",
        "errors",
    ],
    "additionalProperties": False,
}

TOOL_CONTRACT = {
    "name": TOOL_NAME,
    "title": APP_NAME,
    "description": (
        "Use this tool only when the user provides raw requirement text and asks to extract "
        "explicitly stated functional requirements, constraints, acceptance criteria, or missing "
        "fields into structured JSON. The tool must only extract text that is explicitly present "
        "in the source text. Do not use this tool for decision questions, build/no-build questions, "
        "advice, recommendations, implementation planning, code generation, support ticket handling, "
        "form submission, authentication, or saving data. If the input is a decision question such "
        "as 'Should I build this app?', the tool should return a structured out_of_scope error "
        "instead of advice."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "requirements_text": {
                "type": "string",
                "description": "Raw requirement text to extract from.",
            }
        },
        "required": ["requirements_text"],
        "additionalProperties": False,
    },
    "outputSchema": OUTPUT_SCHEMA,
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
}


def _page(title: str, body: str) -> bytes:
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: #1f2933;
      background: #f6f8fb;
      line-height: 1.55;
    }}
    main {{
      max-width: 880px;
      margin: 0 auto;
      padding: 40px 20px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 32px;
      line-height: 1.2;
    }}
    h2 {{
      margin-top: 28px;
      font-size: 20px;
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-top: 24px;
      padding-top: 18px;
      border-top: 1px solid #d9e2ec;
    }}
    a {{
      color: #0b63ce;
    }}
    ul {{
      padding-left: 22px;
    }}
  </style>
</head>
<body>
  <main>
    <section>
      {body}
    </section>
  </main>
</body>
</html>"""
    return html.encode("utf-8")


HOME_HTML = _page(
    APP_NAME,
    f"""
      <h1>{APP_NAME}</h1>
      <p>Requirements Extractor extracts explicitly stated requirement information from raw requirement text into structured JSON.</p>
      <h2>What problem it solves</h2>
      <p>It helps Codex and agent project preparation turn unstructured requirement notes into predictable fields without guessing, advising, or creating new requirements.</p>
      <h2>Basic usage</h2>
      <p>Provide raw requirements text to the MCP tool and it returns functional requirements, constraints, acceptance criteria, missing fields, the original source text, and structured errors when needed.</p>
      <p>Support: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
      <nav>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href="/support">Support</a>
      </nav>
    """,
)

PRIVACY_HTML = _page(
    f"Privacy - {APP_NAME}",
    f"""
      <h1>Privacy Policy</h1>
      <p>{APP_NAME} only processes user-provided requirements text.</p>
      <ul>
        <li>The app uses the input only to return structured extraction results.</li>
        <li>The app does not store user input.</li>
        <li>The app does not create accounts.</li>
        <li>The app does not authenticate users.</li>
        <li>The app does not sell data.</li>
        <li>The app does not perform write actions.</li>
        <li>The app does not submit forms.</li>
        <li>The app does not access external systems.</li>
      </ul>
      <p>Support contact: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
      <nav>
        <a href="/">Home</a>
        <a href="/terms">Terms</a>
        <a href="/support">Support</a>
      </nav>
    """,
)

TERMS_HTML = _page(
    f"Terms - {APP_NAME}",
    f"""
      <h1>Terms of Use</h1>
      <p>{APP_NAME} is a structured requirements extraction utility.</p>
      <ul>
        <li>It extracts explicitly stated information only.</li>
        <li>It does not guarantee that project requirements are complete.</li>
        <li>It does not provide legal, financial, medical, or professional advice.</li>
        <li>It does not make project decisions for users.</li>
        <li>Users must review outputs before use.</li>
      </ul>
      <p>Support contact: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
      <nav>
        <a href="/">Home</a>
        <a href="/privacy">Privacy</a>
        <a href="/support">Support</a>
      </nav>
    """,
)

SUPPORT_HTML = _page(
    f"Support - {APP_NAME}",
    f"""
      <h1>{APP_NAME} Support</h1>
      <p>Support email: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
      <h2>Issues users can report</h2>
      <ul>
        <li>MCP connection problems.</li>
        <li>Unexpected structured extraction output.</li>
        <li>Missing output fields.</li>
        <li>Privacy, terms, or data request questions.</li>
      </ul>
      <h2>What to include</h2>
      <ul>
        <li>A short description of the issue.</li>
        <li>The relevant input text, if it is safe to share.</li>
        <li>The returned structured output or error.</li>
        <li>The date and approximate time of the issue.</li>
      </ul>
      <p>Data request contact: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
      <p>The MCP tool itself does not process support tickets.</p>
      <nav>
        <a href="/">Home</a>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
      </nav>
    """,
)

OUT_OF_SCOPE_PATTERNS = [
    re.compile(r"\bshould\s+i\b", re.IGNORECASE),
    re.compile(r"\bshould\s+we\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+should\s+i\b", re.IGNORECASE),
    re.compile(r"\bwrite\s+(?:the\s+)?code\b", re.IGNORECASE),
    re.compile(r"\bgenerate\s+(?:the\s+)?code\b", re.IGNORECASE),
    re.compile(r"\bimplement\s+(?:this|the)\s+app\b", re.IGNORECASE),
    re.compile(r"\bsubmit\s+(?:this\s+)?form\b", re.IGNORECASE),
    re.compile(r"\bsave\s+the\s+data\b", re.IGNORECASE),
    re.compile(r"\bauthenticate\b", re.IGNORECASE),
    re.compile(r"\blog\s+in\b", re.IGNORECASE),
    re.compile(r"\badvice\b", re.IGNORECASE),
    re.compile(r"\brecommend\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+(?:option|approach)\b", re.IGNORECASE),
]


def _error(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def _empty_output(source_text: str = "") -> Dict[str, Any]:
    return {
        "functional_requirements": [],
        "constraints": [],
        "acceptance_criteria": [],
        "missing_fields": [],
        "source_text": source_text,
        "errors": [],
    }


def _error_output(code: str, message: str, source_text: str = "") -> Dict[str, Any]:
    output = _empty_output(source_text)
    output["errors"] = [_error(code, message)]
    return output


def _missing_field_output() -> Dict[str, Any]:
    output = _error_output("missing_field", "requirements_text is required.", "")
    output["missing_fields"] = ["requirements_text"]
    return output


def _invalid_value_output() -> Dict[str, Any]:
    return _error_output("invalid_value", "requirements_text must be a non-empty string.", "")


def _out_of_scope_output(source_text: str) -> Dict[str, Any]:
    return _error_output(
        "out_of_scope",
        "Input is out of scope for Requirements Extractor. This tool only extracts explicitly stated requirements from raw requirement text.",
        source_text,
    )


def _json_rpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _dedupe_append(items: List[str], value: str) -> None:
    cleaned = _clean_item(value)
    if cleaned and cleaned not in items:
        items.append(cleaned)


def _clean_item(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[\s:;\-]+", "", value)
    value = re.sub(r"[\s.;]+$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _split_sentences(text: str) -> List[str]:
    return [_clean_item(part) for part in re.split(r"(?<=[.!?])\s+", text) if _clean_item(part)]


def _split_and_clause(text: str) -> List[str]:
    return [_clean_item(part) for part in re.split(r"\s+and\s+", text) if _clean_item(part)]


def _extract_after_marker(text: str, marker: str) -> str:
    pattern = re.compile(rf"\b{re.escape(marker)}\b\s*:\s*(.+)", re.IGNORECASE)
    match = pattern.search(text)
    return match.group(1) if match else ""


def _extract_missing_fields(text: str) -> List[str]:
    missing_fields: List[str] = []
    for match in re.finditer(r"\bmissing\s+fields?\s*:\s*([A-Za-z0-9_,\s]+)", text, re.IGNORECASE):
        for field in re.split(r",|\band\b", match.group(1)):
            _dedupe_append(missing_fields, field)
    return missing_fields


def _extract_acceptance_criteria(sentence: str, output: Dict[str, Any]) -> bool:
    marker_text = _extract_after_marker(sentence, "Acceptance criteria")
    if marker_text:
        _dedupe_append(output["acceptance_criteria"], marker_text)
        return True

    if re.match(r"(?i)^output\s+must\s+include\b", sentence):
        _dedupe_append(output["acceptance_criteria"], sentence)
        return True

    return False


def _extract_constraints(sentence: str, output: Dict[str, Any]) -> bool:
    match = re.search(r"\b(must\s+not\s+.+|do\s+not\s+.+|does\s+not\s+.+|must\s+only\s+.+)\b", sentence, re.IGNORECASE)
    if not match:
        return False
    _dedupe_append(output["constraints"], match.group(1))
    return True


def _extract_functional(sentence: str, output: Dict[str, Any]) -> bool:
    lowered = sentence.lower()

    if lowered.startswith("build an app that "):
        _dedupe_append(output["functional_requirements"], sentence[len("Build an app that ") :])
        return True

    if lowered.startswith("create an app that "):
        _dedupe_append(output["functional_requirements"], sentence[len("Create an app that ") :])
        return True

    should_match = re.match(r"(?i)^(?:the\s+)?(?:tool|app|system)\s+should\s+(.+)$", sentence)
    if should_match:
        for item in _split_and_clause(should_match.group(1)):
            _dedupe_append(output["functional_requirements"], item)
        return True

    must_match = re.match(r"(?i)^(?:the\s+)?(?:tool|app|system)\s+must\s+(.+)$", sentence)
    if must_match and " not " not in f" {must_match.group(1).lower()} ":
        _dedupe_append(output["functional_requirements"], must_match.group(1))
        return True

    return False


def _is_out_of_scope(text: str) -> bool:
    return any(pattern.search(text) for pattern in OUT_OF_SCOPE_PATTERNS)


def extract_requirements(requirements_text: str) -> Dict[str, Any]:
    if _is_out_of_scope(requirements_text):
        return _out_of_scope_output(requirements_text)

    output = _empty_output(requirements_text)
    output["missing_fields"] = _extract_missing_fields(requirements_text)

    for sentence in _split_sentences(requirements_text):
        handled = _extract_acceptance_criteria(sentence, output)
        handled = _extract_constraints(sentence, output) or handled
        handled = _extract_functional(sentence, output) or handled

        if not handled and re.search(r"\breturn\s+JSON\b", sentence, re.IGNORECASE):
            _dedupe_append(output["functional_requirements"], "return JSON")

    return output


def _tool_result(structured: Dict[str, Any]) -> Dict[str, Any]:
    text = "Extracted explicitly stated requirements."
    if structured["errors"]:
        text = "Requirements extraction failed with a structured error."

    result = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
    }
    if structured["errors"]:
        result["isError"] = True
    return result


def handle_rpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": APP_NAME, "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [TOOL_CONTRACT]}}

    if method == "tools/call":
        if params.get("name") != TOOL_NAME:
            return _json_rpc_error(request_id, -32602, "Invalid tool name.")

        arguments = params.get("arguments") or {}
        if "requirements_text" not in arguments:
            return {"jsonrpc": "2.0", "id": request_id, "result": _tool_result(_missing_field_output())}

        requirements_text = arguments.get("requirements_text")
        if not isinstance(requirements_text, str) or requirements_text.strip() == "":
            return {"jsonrpc": "2.0", "id": request_id, "result": _tool_result(_invalid_value_output())}

        try:
            structured = extract_requirements(requirements_text)
        except Exception:
            structured = _error_output("internal_error", "An unexpected internal error occurred.", requirements_text)
        return {"jsonrpc": "2.0", "id": request_id, "result": _tool_result(structured)}

    return _json_rpc_error(request_id, -32601, "Method not found.")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, body: Dict[str, Any]) -> None:
        encoded = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(HOME_HTML)
            return
        if self.path == "/privacy":
            self._send_html(PRIVACY_HTML)
            return
        if self.path == "/terms":
            self._send_html(TERMS_HTML)
            return
        if self.path == "/support":
            self._send_html(SUPPORT_HTML)
            return
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/.well-known/openai-apps-challenge":
            self._send_text(200, os.getenv("OPENAI_APPS_CHALLENGE", "test"))
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._send_json(404, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "invalid_json"})
            return

        self._send_json(200, handle_rpc(payload))


def create_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve() -> Tuple[str, int]:
    port = int(os.getenv("PORT", "8000"))
    host = "0.0.0.0"
    print(f"Server running on {host}:{port}")
    server = create_server(host, port)
    server.serve_forever()
    return host, port


if __name__ == "__main__":
    serve()
