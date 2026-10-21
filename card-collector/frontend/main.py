"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/689344436861/locations/us-east1/reasoningEngines/5848463976349827072",
)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


import re

def _handle_a2ui_obj(parsed: Any, out_list: list) -> None:
    if not parsed:
        return
    if isinstance(parsed, bytes):
        try:
            parsed = parsed.decode("utf-8")
        except Exception:
            return
    if isinstance(parsed, str):
        if "<a2a_datapart_json>" in parsed:
            for match in re.finditer(r"<a2a_datapart_json>\s*(.*?)\s*</a2a_datapart_json>", parsed, re.DOTALL):
                try:
                    _handle_a2ui_obj(json.loads(match.group(1)), out_list)
                except Exception:
                    pass
            return
        if "<a2ui-json>" in parsed:
            for match in re.finditer(r"<a2ui-json>\s*(.*?)\s*</a2ui-json>", parsed, re.DOTALL):
                try:
                    _handle_a2ui_obj(json.loads(match.group(1)), out_list)
                except Exception:
                    pass
            return
        try:
            parsed = json.loads(parsed)
        except Exception:
            return

    if isinstance(parsed, list):
        root_id = parsed[0].get("id") if (parsed and isinstance(parsed[0], dict)) else None
        sid = f"surface_{len(out_list)}"
        out_list.append({"kind": "a2ui", "data": {"beginRendering": {"surfaceId": sid, "root": root_id}}})
        out_list.append({"kind": "a2ui", "data": {"surfaceUpdate": {"surfaceId": sid, "components": parsed}}})
    elif isinstance(parsed, dict):
        if "data" in parsed and isinstance(parsed["data"], (dict, list, str, bytes)):
            _handle_a2ui_obj(parsed["data"], out_list)
        elif "beginRendering" in parsed or "surfaceUpdate" in parsed:
            out_list.append({"kind": "a2ui", "data": parsed})
        elif "components" in parsed:
            sid = parsed.get("surfaceId", f"surface_{len(out_list)}")
            comps = parsed.get("components", [])
            root_id = comps[0].get("id") if (comps and isinstance(comps[0], dict)) else None
            out_list.append({"kind": "a2ui", "data": {"beginRendering": {"surfaceId": sid, "root": root_id}}})
            out_list.append({"kind": "a2ui", "data": {"surfaceUpdate": {"surfaceId": sid, "components": comps}}})


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI."""
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        text_val = getattr(root, "text", "") or ""
        if isinstance(root, dict) and "text" in root:
            text_val = root["text"]

        if text_val:
            # Extract all embedded a2ui json or a2a_datapart_json tags
            for match in re.finditer(r"<a2a_datapart_json>\s*(.*?)\s*</a2a_datapart_json>", text_val, re.DOTALL):
                try:
                    parsed = json.loads(match.group(1))
                    _handle_a2ui_obj(parsed, out)
                except Exception:
                    pass
            for match in re.finditer(r"<a2ui-json>\s*(.*?)\s*</a2ui-json>", text_val, re.DOTALL):
                try:
                    parsed = json.loads(match.group(1))
                    _handle_a2ui_obj(parsed, out)
                except Exception:
                    pass
            
            clean_text = re.sub(r"<a2a_datapart_json>.*?</a2a_datapart_json>", "", text_val, flags=re.DOTALL)
            clean_text = re.sub(r"<a2ui-json>.*?</a2ui-json>", "", clean_text, flags=re.DOTALL).strip()
            if clean_text:
                out.append({"kind": "text", "text": clean_text})
        elif getattr(root, "data", None) is not None:
            data_val = root.data
            _handle_a2ui_obj(data_val, out)
        elif isinstance(root, dict) and "data" in root:
            _handle_a2ui_obj(root["data"], out)
        elif getattr(root, "file", None) is not None:
            uri = getattr(root.file, "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
        elif isinstance(root, dict) and "url" in root:
            out.append({"kind": "text", "text": root["url"]})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        async for event in a2a_client.send_message(msg):
            if isinstance(event, tuple):
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    parts.extend(_extract_parts(update.artifact.parts))
                elif isinstance(update, Message) or hasattr(update, "parts"):
                    parts.extend(_extract_parts(update.parts))
            elif hasattr(event, "artifacts"):
                last_task = event

        if not parts and last_task is not None:
            if getattr(last_task, "artifacts", None):
                for artifact in last_task.artifacts:
                    parts.extend(_extract_parts(artifact.parts))
            if not parts and getattr(last_task, "history", None):
                for m in reversed(last_task.history):
                    if getattr(m, "role", None) != Role.user and getattr(m, "parts", None):
                        parts.extend(_extract_parts(m.parts))
                        break

        if not parts:
            parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
