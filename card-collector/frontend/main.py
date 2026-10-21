"""FastAPI proxy for deployed A2A agent (Agent Runtime, agents-cli 1.1.0+)."""

import json
import os
import google.auth
import google.auth.transport.requests
from google.protobuf.json_format import MessageToDict, ParseDict
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.helpers import new_text_message
from a2a.types import (
    AgentCard,
    SendMessageConfiguration,
    SendMessageRequest,
    TaskArtifactUpdateEvent,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/689344436861/locations/us-east1/reasoningEngines/5848463976349827072",
)
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"
_A2UI_MIME = "application/json+a2ui"

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
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        data = resp.json()
        card = ParseDict(data, AgentCard(), ignore_unknown_fields=True)
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        p_dict = MessageToDict(p) if hasattr(p, "DESCRIPTOR") else (p if isinstance(p, dict) else {})
        if "text" in p_dict and p_dict["text"]:
            out.append({"kind": "text", "text": p_dict["text"]})
        elif "data" in p_dict and p_dict["data"]:
            meta = p_dict.get("metadata", {})
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            data_val = p_dict["data"]
            if isinstance(data_val, str):
                try:
                    data_val = json.loads(data_val)
                except Exception:
                    pass
            if mime == _A2UI_MIME or isinstance(data_val, dict):
                out.append({"kind": "a2ui", "data": data_val})
        elif "url" in p_dict and p_dict["url"]:
            out.append({"kind": "text", "text": p_dict["url"]})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(ClientConfig(httpx_client=client))
        a2a_client = factory.create(card)

        msg = new_text_message(
            text=message,
            context_id=_contexts.get(user_id),
        )
        send_req = SendMessageRequest(message=msg, configuration=SendMessageConfiguration())

        async for event in a2a_client.send_message(send_req):
            if isinstance(event, tuple):
                task, update = event
                if task is not None and getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    parts.extend(_extract_parts(update.artifact.parts))
            elif hasattr(event, "DESCRIPTOR"):
                if event.HasField("artifact_update"):
                    if event.artifact_update.context_id:
                        _contexts[user_id] = event.artifact_update.context_id
                    parts.extend(_extract_parts(event.artifact_update.artifact.parts))
                elif event.HasField("status_update"):
                    if event.status_update.context_id:
                        _contexts[user_id] = event.status_update.context_id
                    if event.status_update.status.HasField("message"):
                        parts.extend(_extract_parts(event.status_update.status.message.parts))
                elif event.HasField("task"):
                    if event.task.context_id:
                        _contexts[user_id] = event.task.context_id
                    for artifact in event.task.artifacts:
                        parts.extend(_extract_parts(artifact.parts))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
