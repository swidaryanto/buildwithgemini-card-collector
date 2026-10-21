# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import random
from typing import Any, Optional
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.tool_context import ToolContext
from google.cloud import firestore, storage
from google.genai import Client as GenAIClient
from google.genai import types

from a2ui.core.basic_catalog.v0_8 import BasicCatalog
from a2ui.inference_formats.direct_json import DirectJsonPromptGenerator

from .a2ui_utils import a2ui_callback

MODEL = "gemini-2.5-flash"
PROJECT_ID = "qwiklabs-gcp-04-b661fd22d876"
COLLECTION_NAME = "cards"
IMAGE_BUCKET_NAME = "snap-tcg-cards-b661fd"
IMAGE_MODEL = "gemini-3.1-flash-lite-image"
IMAGE_LOCATION = "global"
VIDEO_MODEL = "gemini-omni-flash-preview"
VIDEO_LOCATION = "global"
AGENT_ENGINE_RESOURCE = (
    "projects/689344436861/locations/us-east1/reasoningEngines/3263679265215873024"
)
MEMORY_BANK_ID = "3263679265215873024"


def _get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def list_cards(element: str = "", rarity: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Lists collectible cards from the catalog with optional filtering by element or rarity.

    Args:
        element: Optional filter for card element (e.g. 'Fire', 'Water', 'Earth', 'Electric', 'Dark', 'Wind', 'Nature', 'Cosmic').
        rarity: Optional filter for card rarity (e.g. 'Common', 'Uncommon', 'Rare', 'Epic', 'Legendary', 'Mythic').
        limit: Maximum number of cards to return (default 10).

    Returns:
        A list of card dictionaries containing card stats, elements, and descriptions.
    """
    db = _get_firestore_client()
    query = db.collection(COLLECTION_NAME)
    if element:
        query = query.where("element", "==", element.capitalize())
    if rarity:
        query = query.where("rarity", "==", rarity.capitalize())

    docs = query.limit(limit).stream()
    cards = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        cards.append(data)
    return cards


def get_card(card_name_or_id: str) -> dict[str, Any]:
    """Retrieves detailed information for a specific collectible card by name or document ID.

    Args:
        card_name_or_id: The name of the card (e.g. 'Ignis Drake') or the document ID (e.g. 'card_001').

    Returns:
        A dictionary with the card's full stats (hp, attack, defense, speed, ability, price) or error message.
    """
    db = _get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(card_name_or_id)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        return data

    # Fallback to case-insensitive name search
    target_lower = card_name_or_id.strip().lower()
    for card_doc in db.collection(COLLECTION_NAME).stream():
        data = card_doc.to_dict() or {}
        if data.get("name", "").lower() == target_lower:
            data["id"] = card_doc.id
            return data

    return {"error": f"Card '{card_name_or_id}' not found in the catalog."}


def add_card(
    name: str,
    element: str,
    rarity: str,
    hp: int,
    attack: int,
    defense: int,
    speed: int,
    ability: str,
    description: str,
    price: int = 100,
) -> dict[str, Any]:
    """Adds a new collectible creature card to the Firestore catalog.

    Args:
        name: Name of the creature/card (e.g. 'Solar Phoenix').
        element: Element type (e.g. 'Fire', 'Water', 'Earth', 'Electric', 'Dark', 'Wind', 'Nature', 'Cosmic').
        rarity: Rarity tier ('Common', 'Uncommon', 'Rare', 'Epic', 'Legendary', 'Mythic').
        hp: Health points integer (e.g. 100).
        attack: Attack power integer (e.g. 80).
        defense: Defense stat integer (e.g. 70).
        speed: Speed stat integer (e.g. 90).
        ability: Special skill or move description.
        description: Lore or background description of the creature.
        price: Market price in coins/credits (default 100).

    Returns:
        A dictionary confirming creation and containing the card's document ID and data.
    """
    db = _get_firestore_client()
    doc_id = "card_" + name.lower().replace(" ", "_")
    card_data = {
        "id": doc_id,
        "name": name,
        "element": element.capitalize(),
        "rarity": rarity.capitalize(),
        "hp": int(hp),
        "attack": int(attack),
        "defense": int(defense),
        "speed": int(speed),
        "ability": ability,
        "description": description,
        "price": int(price),
        "in_stock": True,
    }
    db.collection(COLLECTION_NAME).document(doc_id).set(card_data)
    return {"status": "success", "message": f"Card '{name}' added successfully.", "card": card_data}


def update_card(
    card_name_or_id: str,
    price: int = -1,
    in_stock: Optional[bool] = None,
    ability: str = "",
) -> dict[str, Any]:
    """Updates specific fields of an existing card in the catalog.

    Args:
        card_name_or_id: The name of the card or its document ID.
        price: New price in coins (leave -1 to keep unchanged).
        in_stock: Whether the card is available in stock.
        ability: New ability description if modified.

    Returns:
        A dictionary with the update status and updated card fields.
    """
    db = _get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(card_name_or_id)
    doc = doc_ref.get()

    doc_id = card_name_or_id
    if not doc.exists:
        target_lower = card_name_or_id.strip().lower()
        found = False
        for card_doc in db.collection(COLLECTION_NAME).stream():
            data = card_doc.to_dict() or {}
            if data.get("name", "").lower() == target_lower:
                doc_id = card_doc.id
                doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
                found = True
                break
        if not found:
            return {"error": f"Card '{card_name_or_id}' not found for update."}

    updates: dict[str, Any] = {}
    if price >= 0:
        updates["price"] = price
    if in_stock is not None:
        updates["in_stock"] = in_stock
    if ability:
        updates["ability"] = ability

    if updates:
        doc_ref.update(updates)
        return {"status": "success", "message": f"Updated card '{doc_id}' with {updates}."}
    return {"status": "no_change", "message": "No valid fields provided to update."}


def open_booster_pack(pack_type: str = "standard") -> dict[str, Any]:
    """Opens a virtual booster pack containing 3 random collectible creature cards from the catalog, including their visual illustrations and image URLs.

    Args:
        pack_type: Type of booster pack (e.g. 'standard', 'elemental', 'premium').

    Returns:
        A dictionary containing the pulled cards, card details (name, element, rarity, stats, image_url), and pack summary.
    """
    db = _get_firestore_client()
    docs = list(db.collection(COLLECTION_NAME).stream())

    if not docs:
        return {"error": "No cards found in the catalog to open a pack."}

    all_cards = []
    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        all_cards.append(data)

    pack_size = min(3, len(all_cards))
    pulled_cards = random.sample(all_cards, k=pack_size)

    return {
        "status": "success",
        "pack_type": pack_type,
        "cards_drawn_count": len(pulled_cards),
        "cards": pulled_cards,
        "message": f"🎉 You opened a {pack_type} booster pack and revealed {len(pulled_cards)} creature cards!",
    }


def lookup_external_creature(name: str) -> dict[str, Any]:
    """Looks up real creature data, competitive stats, elements, and official artwork from the free public PokéAPI.

    Args:
        name: Name or Pokedex ID of the creature (e.g. 'pikachu', 'charizard', 'mewtwo', 'gengar', 'lucario').

    Returns:
        A dictionary containing creature stats (HP, Attack, Defense, Speed), elements, abilities, and artwork URL.
    """
    clean_name = name.strip().lower().replace(" ", "-")
    url = f"https://pokeapi.co/api/v2/pokemon/{clean_name}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CardCollectorAgent/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        types_list = [t["type"]["name"].capitalize() for t in data.get("types", [])]
        stats = {s["stat"]["name"]: s["base_stat"] for s in data.get("stats", [])}
        abilities = [a["ability"]["name"].replace("-", " ").capitalize() for a in data.get("abilities", [])]

        sprites = data.get("sprites", {})
        other_sprites = sprites.get("other", {})
        artwork = other_sprites.get("official-artwork", {}).get("front_default") or sprites.get("front_default")

        return {
            "status": "success",
            "name": data.get("name", name).capitalize(),
            "pokedex_id": data.get("id"),
            "elements": types_list,
            "hp": stats.get("hp", 50),
            "attack": stats.get("attack", 50),
            "defense": stats.get("defense", 50),
            "speed": stats.get("speed", 50),
            "special_attack": stats.get("special-attack", 50),
            "special_defense": stats.get("special-defense", 50),
            "abilities": abilities,
            "artwork_url": artwork,
            "height_m": data.get("height", 0) / 10,
            "weight_kg": data.get("weight", 0) / 10,
            "source": "PokéAPI (Free Public API)",
        }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Creature '{name}' was not found in the public database."}
        return {"error": f"HTTP error {e.code} while querying public API."}
    except Exception as e:
        return {"error": f"Failed to fetch external creature data: {str(e)}"}


async def generate_card_artwork(
    card_name: str,
    visual_description: str,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Generates custom creature artwork for a collectible trading card using the gemini-3.1-flash-lite-image model, saves it as an artifact, and uploads it to Cloud Storage.

    Args:
        card_name: Name of the creature or card (e.g. 'Solar Phoenix', 'Frost Wyrm').
        visual_description: Detailed visual description of the creature, pose, lighting, background, and elemental effects.

    Returns:
        A dictionary containing the public image URL, card name, artifact name, and upload status.
    """
    prompt = (
        f"A vibrant, highly detailed collectible trading card illustration of {card_name}. "
        f"{visual_description}. Masterpiece fantasy digital card art, centered creature composition, dramatic lighting."
    )

    try:
        genai_client = GenAIClient(vertexai=True, project=PROJECT_ID, location=IMAGE_LOCATION)
        response = genai_client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "No image data was generated by the model."}

        clean_name = card_name.lower().replace(" ", "_")
        filename = f"{clean_name}.jpg"
        artifact_saved = False

        # 1. Save artifact for playground UI if tool_context is provided
        if tool_context is not None:
            try:
                artifact_part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes))
                await tool_context.save_artifact(filename, artifact_part)
                artifact_saved = True
            except Exception:
                pass

        # 2. Upload to Cloud Storage bucket for permanent public URL
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        blob_path = f"cards/{clean_name}_{timestamp}.jpg"
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(IMAGE_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{IMAGE_BUCKET_NAME}/{blob_path}"

        return {
            "status": "success",
            "card_name": card_name,
            "public_url": public_url,
            "artifact_name": filename,
            "artifact_saved": artifact_saved,
            "message": f"Successfully generated artwork for '{card_name}'.",
        }
    except Exception as e:
        return {"error": f"Failed to generate card artwork: {str(e)}"}


async def generate_card_video(
    card_name: str,
    animation_description: str,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Generates a short animated video for a collectible creature card using Google's Omni model (gemini-omni-flash-preview) in the global region, saves it as an artifact, and uploads it to Cloud Storage.

    Args:
        card_name: Name of the creature or card (e.g. 'Solar Phoenix', 'Frost Wyrm').
        animation_description: Description of the animation, motion, elemental attacks, or creature actions.

    Returns:
        A dictionary containing the public video URL, card name, artifact name, and upload status.
    """
    prompt = (
        f"A cinematic 3-second animated card visualization of {card_name}. "
        f"{animation_description}. Dynamic motion, vivid elemental particle effects, fantasy trading card animation."
    )

    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        authed_session = AuthorizedSession(credentials)

        url = f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{VIDEO_LOCATION}/interactions"
        payload = {
            "model": VIDEO_MODEL,
            "input": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
            "response_format": [
                {
                    "type": "video",
                    "aspect_ratio": "16:9",
                    "duration": "3s",
                }
            ],
            "generation_config": {
                "video_config": {
                    "task": "text_to_video",
                }
            },
        }

        resp = authed_session.post(url, json=payload, timeout=180)
        if resp.status_code != 200:
            return {"error": f"Interactions API returned status {resp.status_code}: {resp.text}"}

        data = resp.json()
        video_bytes = None
        mime_type = "video/mp4"

        for step in data.get("steps", []):
            if step.get("type") == "model_output":
                for content in step.get("content", []):
                    if content.get("type") == "video":
                        mime_type = content.get("mime_type") or "video/mp4"
                        if "data" in content:
                            video_bytes = base64.b64decode(content["data"])
                            break
                if video_bytes:
                    break

        if not video_bytes:
            return {"error": "No video data found in the model response."}

        clean_name = card_name.lower().replace(" ", "_")
        filename = f"{clean_name}.mp4"
        artifact_saved = False

        # 1. Save artifact for playground UI if tool_context is provided
        if tool_context is not None:
            try:
                artifact_part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=video_bytes))
                await tool_context.save_artifact(filename, artifact_part)
                artifact_saved = True
            except Exception:
                pass

        # 2. Upload to Cloud Storage bucket for permanent public URL
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        blob_path = f"videos/{clean_name}_{timestamp}.mp4"
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(IMAGE_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{IMAGE_BUCKET_NAME}/{blob_path}"

        return {
            "status": "success",
            "card_name": card_name,
            "public_url": public_url,
            "artifact_name": filename,
            "artifact_saved": artifact_saved,
            "message": f"Successfully generated video animation for '{card_name}'.",
        }
    except Exception as e:
        return {"error": f"Failed to generate card video: {str(e)}"}


async def generate_memories_callback(callback_context: CallbackContext) -> None:
    """Callback to extract durable user facts and preferences to Memory Bank after each turn."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def _build_a2ui_instruction() -> str:
    """Generates the A2UI v0.8 system prompt with BasicCatalog and TCG guidelines."""
    generator = DirectJsonPromptGenerator(catalogs=[BasicCatalog()])
    schema_prompt = generator.generate()
    role_description = (
        "You are the Card Collector Companion, an expert AI assistant dedicated to helping "
        "collectors discover, trade, analyze, and manage collectible creature cards."
    )
    workflow_description = (
        "Analyze the user's request and return structured A2UI UI when presenting cards, "
        "booster packs, or creature stats. When conversational answers are needed, you may "
        "include brief text alongside A2UI components."
    )
    ui_guidelines = (
        "UI Guidelines for adk web rendering:\n"
        "- Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows.\n"
        "- Never nest a Card inside a Card.\n"
        "- Use ONLY these components: Card, Column, Row, Text, Divider, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do nothing in adk web).\n"
        "- Always include an Image component inside each card whenever a card has an `image_url` (from open_booster_pack, list_cards, get_card, generate_card_artwork, or lookup_external_creature). "
        "Set the Image url to that exact https link: {\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. "
        "Never point an Image at a bare filename, an artifact name, or a non-http(s) path. If you do not have a public URL, add a short Text line noting the image instead.\n"
        "- No markdown in text; use the usageHint property ('h1', 'h2', 'body') for headings and emphasis.\n"
        "- Output A2UI JSON array wrapped in <a2ui-json>...</a2ui-json> tags.\n"
    )
    tools_description = (
        "Available Tools:\n"
        "- `generate_card_artwork`: Generate vibrant fantasy artwork for any creature using the image generation model, saving it as an artifact and returning its public URL.\n"
        "- `generate_card_video`: Generate a short animated video for any creature card using the Gemini Omni model (gemini-omni-flash-preview), saving it as an artifact and returning its public URL.\n"
        "- `open_booster_pack`: Open a booster pack to reveal 3 exciting creature cards drawn from the database, each with complete stats and visual artwork image_url.\n"
        "- `lookup_external_creature`: Query the free public PokéAPI to scout real creature stats, types, abilities, and official artwork.\n"
        "- `list_cards`: Browse and filter cards by element (Fire, Water, Earth, Electric, Dark, Wind, Nature, Cosmic) or rarity (Common, Uncommon, Rare, Epic, Legendary, Mythic).\n"
        "- `get_card`: Retrieve full stats, abilities, and descriptions for any specific card in your local Firestore catalog.\n"
        "- `add_card`: Register newly discovered or custom-designed creature cards into Firestore.\n"
        "- `update_card`: Update prices, stock availability, or abilities in Firestore.\n"
    )
    return (
        f"{role_description}\n\n"
        f"{workflow_description}\n\n"
        f"{ui_guidelines}\n\n"
        f"{tools_description}\n\n"
        f"{schema_prompt}"
    )


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=_build_a2ui_instruction(),
    tools=[
        PreloadMemoryTool(),
        generate_card_artwork,
        generate_card_video,
        open_booster_pack,
        lookup_external_creature,
        list_cards,
        get_card,
        add_card,
        update_card,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
