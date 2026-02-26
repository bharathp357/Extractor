"""
MCP (Model Context Protocol) Server — AI Command Center.
Exposes multi-provider AI tools via JSON-RPC over stdio/HTTP.
"""
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from providers import get_automator, get_all_statuses, get_available_providers
from storage import get_storage
import config


# ─────────────────────────────────────────────────────────────
# MCP Tool Definitions
# ─────────────────────────────────────────────────────────────

MCP_SERVER_INFO = {
    "name": "ai-command-center",
    "version": "2.0.0",
    "description": "Multi-provider AI scraper — Google AI Mode, Gemini Pro, ChatGPT. Routes queries, scrapes responses, manages conversations."
}

MCP_TOOLS = [
    {
        "name": "send_prompt",
        "description": "Send a query to an AI provider (google, gemini, chatgpt). Scrapes the full generated response.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The query to send"
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name: google, gemini, or chatgpt (default: google)",
                    "default": "google"
                },
                "followup": {
                    "type": "boolean",
                    "description": "If true, send as follow-up within existing conversation (default: false)",
                    "default": False
                },
                "save": {
                    "type": "boolean",
                    "description": "Whether to save the conversation to a text file (default: true)",
                    "default": True
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "get_status",
        "description": "Check connection status of all providers or a specific one",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Optional: specific provider to check (default: all)"
                }
            }
        }
    },
    {
        "name": "new_conversation",
        "description": "Reset conversation state for a provider so next prompt starts fresh",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider name (default: google)",
                    "default": "google"
                }
            }
        }
    },
    {
        "name": "reconnect",
        "description": "Reconnect a provider by closing and reopening its tab",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider name (default: google)",
                    "default": "google"
                }
            }
        }
    },
    {
        "name": "list_conversations",
        "description": "List all saved conversation files",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "read_conversation",
        "description": "Read the contents of a saved conversation file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The filename of the conversation to read"
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "list_providers",
        "description": "List all available AI providers and their init status",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ─────────────────────────────────────────────────────────────
# MCP Tool Execution
# ─────────────────────────────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute an MCP tool and return the result."""
    storage = get_storage()

    if tool_name == "send_prompt":
        prompt = arguments.get("prompt", "")
        provider = arguments.get("provider", "google")
        followup = arguments.get("followup", False)
        save = arguments.get("save", True)

        if not prompt:
            return {"error": "Empty prompt provided"}

        try:
            automator = get_automator(provider)
        except ValueError as e:
            return {"error": str(e)}

        if followup:
            result = automator.send_followup(prompt)
        else:
            result = automator.send_and_get_response(prompt)

        if save and result["success"]:
            filepath = storage.save_conversation(
                prompt=result["prompt"],
                response=result["response"],
                metadata={
                    "timestamp": result["timestamp"],
                    "provider": result.get("provider", provider),
                }
            )
            result["saved_to"] = filepath

        return result

    elif tool_name == "get_status":
        provider = arguments.get("provider", "")
        if provider:
            try:
                automator = get_automator(provider)
                return automator.get_status()
            except ValueError as e:
                return {"error": str(e)}
        return get_all_statuses()

    elif tool_name == "new_conversation":
        provider = arguments.get("provider", "google")
        try:
            automator = get_automator(provider)
            automator.new_conversation()
            return {"success": True, "provider": provider}
        except ValueError as e:
            return {"error": str(e)}

    elif tool_name == "reconnect":
        provider = arguments.get("provider", "google")
        try:
            automator = get_automator(provider)
            automator.reconnect()
            return automator.get_status()
        except ValueError as e:
            return {"error": str(e)}

    elif tool_name == "list_conversations":
        return {"conversations": storage.list_conversations()}

    elif tool_name == "read_conversation":
        filename = arguments.get("filename", "")
        content = storage.read_conversation(filename)
        if content:
            return {"filename": filename, "content": content}
        return {"error": f"File not found: {filename}"}

    elif tool_name == "list_providers":
        return {"providers": get_available_providers()}

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ─────────────────────────────────────────────────────────────
# JSON-RPC Handler (MCP Protocol over HTTP)
# ─────────────────────────────────────────────────────────────

class MCPRequestHandler(BaseHTTPRequestHandler):
    """Handle MCP JSON-RPC requests over HTTP."""

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error(-32700, "Parse error")
            return

        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        response = self._handle_method(method, params, req_id)
        self._send_response(response)

    def _handle_method(self, method: str, params: dict, req_id) -> dict:
        """Route JSON-RPC methods to handlers."""

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": MCP_SERVER_INFO,
                    "capabilities": {
                        "tools": {"listChanged": False}
                    }
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS}
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = execute_tool(tool_name, arguments)

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {}
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    def _send_response(self, response: dict):
        body = json.dumps(response).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, message: str):
        response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": code, "message": message}
        }
        self._send_response(response)

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass


# ─────────────────────────────────────────────────────────────
# STDIO Mode (for direct MCP client integration)
# ─────────────────────────────────────────────────────────────

def run_stdio_mode():
    """Run MCP server in stdio mode (reads JSON-RPC from stdin, writes to stdout)."""
    print(f"[MCP] Starting stdio mode...", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            method = request.get("method", "")
            params = request.get("params", {})
            req_id = request.get("id")

            handler = MCPRequestHandler.__new__(MCPRequestHandler)
            response = handler._handle_method(method, params, req_id)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()


# ─────────────────────────────────────────────────────────────
# HTTP Mode
# ─────────────────────────────────────────────────────────────

def run_mcp_server():
    """Run MCP server over HTTP."""
    server = HTTPServer((config.MCP_HOST, config.MCP_PORT), MCPRequestHandler)
    print(f"[MCP] Server running at http://{config.MCP_HOST}:{config.MCP_PORT}")
    print(f"[MCP] Tools available: {[t['name'] for t in MCP_TOOLS]}")
    server.serve_forever()


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        run_stdio_mode()
    else:
        run_mcp_server()
