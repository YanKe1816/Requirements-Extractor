import json
import threading
import urllib.error
import urllib.request

from server import OUTPUT_FIELDS, TOOL_NAME, create_server

server = None
port = None


def setup_module(_module):
    global server, port
    server = create_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def teardown_module(_module):
    server.shutdown()
    server.server_close()


def request(method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode("utf-8"), dict(resp.headers)


def rpc(method, params=None, req_id=1):
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    status, raw, _headers = request("POST", "/mcp", payload)
    return status, json.loads(raw)


def call_tool(arguments, req_id=1):
    return rpc("tools/call", {"name": TOOL_NAME, "arguments": arguments}, req_id)


def structured(data):
    return data["result"]["structuredContent"]


def assert_output_shape(content):
    assert set(content) == OUTPUT_FIELDS
    assert isinstance(content["functional_requirements"], list)
    assert isinstance(content["constraints"], list)
    assert isinstance(content["acceptance_criteria"], list)
    assert isinstance(content["missing_fields"], list)
    assert isinstance(content["source_text"], str)
    assert isinstance(content["errors"], list)
    for error in content["errors"]:
        assert set(error) == {"code", "message"}
        assert error["code"] in {"missing_field", "invalid_value", "out_of_scope", "internal_error"}


def test_mcp_server_can_start_and_get_root_works():
    status, body, headers = request("GET", "/")
    assert status == 200
    assert "text/plain" in headers["Content-Type"]
    assert "Requirements Extractor MCP server" == body


def test_get_health_works():
    status, body, _headers = request("GET", "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_get_mcp_is_not_mcp_endpoint():
    try:
        request("GET", "/mcp")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    else:
        raise AssertionError("GET /mcp should not accept MCP requests")


def test_initialize_returns_required_fields():
    status, data = rpc("initialize")
    assert status == 200
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"] == {"name": "Requirements Extractor", "version": "1.0.0"}
    assert "capabilities" in result


def test_tools_list_returns_one_complete_tool_contract():
    status, data = rpc("tools/list")
    assert status == 200
    tools = data["result"]["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "extract_requirements"
    assert tool["title"] == "Requirements Extractor"
    assert "Use this tool only when the user provides raw requirement text" in tool["description"]
    assert "decision question such as 'Should I build this app?'" in tool["description"]
    assert "instead of advice" in tool["description"]
    assert "inputSchema" in tool
    assert "outputSchema" in tool
    assert "annotations" in tool
    assert tool["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    }


def test_tools_list_input_schema_is_complete():
    _status, data = rpc("tools/list")
    input_schema = data["result"]["tools"][0]["inputSchema"]
    assert input_schema == {
        "type": "object",
        "properties": {
            "requirements_text": {
                "type": "string",
                "description": "Raw requirement text to extract from.",
            }
        },
        "required": ["requirements_text"],
        "additionalProperties": False,
    }


def test_tools_list_output_schema_is_complete():
    _status, data = rpc("tools/list")
    output_schema = data["result"]["tools"][0]["outputSchema"]
    assert output_schema["type"] == "object"
    assert output_schema["required"] == [
        "functional_requirements",
        "constraints",
        "acceptance_criteria",
        "missing_fields",
        "source_text",
        "errors",
    ]
    assert output_schema["additionalProperties"] is False
    assert set(output_schema["properties"]) == OUTPUT_FIELDS
    assert output_schema["properties"]["errors"]["items"]["properties"]["code"]["enum"] == [
        "missing_field",
        "invalid_value",
        "out_of_scope",
        "internal_error",
    ]


def test_positive_1_exact_expected_structured_content():
    text = (
        "Build an app that extracts functional requirements, constraints, and acceptance criteria "
        "from requirement text. It must not save data."
    )
    _status, data = call_tool({"requirements_text": text})
    assert set(data["result"]) == {"content", "structuredContent"}
    assert structured(data) == {
        "functional_requirements": [
            "extracts functional requirements, constraints, and acceptance criteria from requirement text"
        ],
        "constraints": ["must not save data"],
        "acceptance_criteria": [],
        "missing_fields": [],
        "source_text": text,
        "errors": [],
    }


def test_positive_2_extracts_expected_fields():
    text = (
        "The tool should read a project brief and return JSON. Acceptance criteria: output must "
        "include functional requirements and constraints."
    )
    _status, data = call_tool({"requirements_text": text})
    content = structured(data)
    assert_output_shape(content)
    assert content["functional_requirements"] == ["read a project brief", "return JSON"]
    assert content["constraints"] == []
    assert content["acceptance_criteria"] == ["output must include functional requirements and constraints"]
    assert content["missing_fields"] == []
    assert content["source_text"] == text
    assert content["errors"] == []


def test_positive_3_extracts_explicit_output_information_and_preserves_source():
    text = (
        "Input is requirements_text. Output must include functional_requirements, constraints, "
        "acceptance_criteria, missing_fields, source_text, and errors."
    )
    _status, data = call_tool({"requirements_text": text})
    content = structured(data)
    assert_output_shape(content)
    assert content["acceptance_criteria"] == [
        "Output must include functional_requirements, constraints, acceptance_criteria, missing_fields, source_text, and errors"
    ]
    assert content["missing_fields"] == []
    assert content["source_text"] == text
    assert content["errors"] == []


def test_missing_requirements_text_returns_fixed_missing_field_error():
    _status, data = call_tool({})
    content = structured(data)
    assert_output_shape(content)
    assert data["result"]["isError"] is True
    assert content == {
        "functional_requirements": [],
        "constraints": [],
        "acceptance_criteria": [],
        "missing_fields": ["requirements_text"],
        "source_text": "",
        "errors": [{"code": "missing_field", "message": "requirements_text is required."}],
    }


def test_empty_or_invalid_requirements_text_returns_fixed_invalid_value_error():
    for value in ("", "   ", None, 123, []):
        _status, data = call_tool({"requirements_text": value})
        content = structured(data)
        assert_output_shape(content)
        assert data["result"]["isError"] is True
        assert content == {
            "functional_requirements": [],
            "constraints": [],
            "acceptance_criteria": [],
            "missing_fields": [],
            "source_text": "",
            "errors": [
                {"code": "invalid_value", "message": "requirements_text must be a non-empty string."}
            ],
        }


def test_negative_advice_request_returns_out_of_scope_without_advice():
    _status, data = call_tool({"requirements_text": "Should I build this app?"})
    content = structured(data)
    assert_output_shape(content)
    assert data["result"]["isError"] is True
    assert content["errors"][0]["code"] == "out_of_scope"
    assert content["errors"][0]["message"] == (
        "Input is out of scope for Requirements Extractor. This tool only extracts explicitly stated requirements from raw requirement text."
    )
    assert content["functional_requirements"] == []
    assert data["result"]["content"] == [
        {"type": "text", "text": "Requirements extraction failed with a structured error."}
    ]
    serialized = json.dumps(data).lower()
    assert "you should" not in serialized
    assert "probably" not in serialized
    assert "next step" not in serialized


def test_negative_what_should_we_build_next_returns_out_of_scope():
    _status, data = call_tool({"requirements_text": "What should we build next?"})
    content = structured(data)
    assert_output_shape(content)
    assert data["result"]["isError"] is True
    assert content["errors"][0]["code"] == "out_of_scope"
    assert content["functional_requirements"] == []


def test_error_content_text_is_structured_error_message():
    _status, data = call_tool({"requirements_text": "Should I build this app?"})
    assert data["result"]["content"] == [
        {"type": "text", "text": "Requirements extraction failed with a structured error."}
    ]


def test_negative_code_request_returns_out_of_scope_without_code():
    _status, data = call_tool({"requirements_text": "Write the code for this app."})
    content = structured(data)
    assert_output_shape(content)
    assert data["result"]["isError"] is True
    assert content["errors"][0]["code"] == "out_of_scope"
    assert "```" not in json.dumps(data)


def test_negative_form_submit_save_request_returns_out_of_scope():
    _status, data = call_tool({"requirements_text": "Please submit this form and save the data."})
    content = structured(data)
    assert_output_shape(content)
    assert data["result"]["isError"] is True
    assert content["errors"][0]["code"] == "out_of_scope"
    assert content["functional_requirements"] == []


def test_post_mcp_handles_unknown_json_rpc_method():
    _status, data = rpc("unknown/method")
    assert data["error"]["code"] == -32601


def test_tool_call_requires_correct_tool_name():
    _status, data = rpc("tools/call", {"name": "wrong_tool", "arguments": {"requirements_text": "x"}})
    assert data["error"]["code"] == -32602


def test_same_input_called_three_times_returns_stable_output():
    params = {
        "name": TOOL_NAME,
        "arguments": {
            "requirements_text": (
                "The tool should read a project brief and return JSON. Acceptance criteria: output must "
                "include functional requirements and constraints."
            )
        },
    }
    _s1, d1 = rpc("tools/call", params, 101)
    _s2, d2 = rpc("tools/call", params, 102)
    _s3, d3 = rpc("tools/call", params, 103)
    assert structured(d1) == structured(d2) == structured(d3)


def test_tool_output_matches_schema_field_set_on_success_and_errors():
    success_text = "Build an app that extracts functional requirements from requirement text."
    for arguments in ({"requirements_text": success_text}, {}, {"requirements_text": "Should I build this app?"}):
        _status, data = call_tool(arguments)
        assert_output_shape(structured(data))
