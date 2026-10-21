# 🎴 Card Collector AI Companion

An agentic AI assistant built with Google Agent Development Kit (ADK) and Gemini on Google Cloud. Card Collector helps trading card enthusiasts discover collectible creature cards, open booster packs, manage and update the card catalog, look up external creature stats, generate custom digital card artwork, and interact through rich A2UI cards.

---

## 🌟 Features & Implemented Capabilities

### 🗄️ Firestore Card Catalog & Database Management
- **`list_cards`**: Browse and filter collectible creature cards in Firestore by element (`Fire`, `Water`, `Earth`, `Electric`, `Dark`, `Wind`, `Nature`, `Cosmic`) and rarity tier (`Common`, `Uncommon`, `Rare`, `Epic`, `Legendary`, `Mythic`).
- **`get_card`**: Retrieve complete combat stats (`hp`, `attack`, `defense`, `speed`), abilities, price, and lore for any card by document ID or card name.
- **`add_card`**: Insert newly discovered or custom creature cards into the Firestore `cards` collection.
- **`update_card`**: Update card pricing, stock availability, and special abilities in the catalog.

### 🎁 Booster Pack Simulation
- **`open_booster_pack`**: Simulates opening virtual booster packs (e.g., standard, elemental, premium) drawing random creature cards directly from the Firestore card collection.

### 🎨 AI Creature Artwork Generation & Cloud Storage
- **`generate_card_artwork`**: Generates high-quality fantasy digital card illustrations using Vertex AI's `gemini-3.1-flash-lite-image` model.
- Automatically saves images as local ADK artifacts and uploads them to **Google Cloud Storage** (`snap-tcg-cards-b661fd`) to provide public image URLs for UI rendering.

### 🌐 External Creature Scout (PokéAPI)
- **`lookup_external_creature`**: Fetches real-world creature statistics, types, abilities, and official artwork from the free public PokéAPI.

### 🧠 Cross-Session Long-Term Memory
- Powered by **Vertex AI Agent Platform Memory Bank**.
- Incorporates `PreloadMemoryTool` and an `after_agent_callback` (`generate_memories_callback`) to automatically persist collector preferences, favorite elements, and interaction history across sessions.

### 🪟 Agent-to-User Interface (A2UI)
- Configured with A2UI v0.8 `BasicCatalog` and an `after_model_callback` (`a2ui_callback`).
- Renders structured UI components (Cards, Columns, Rows, Text, Dividers, and public Cloud Storage Images) in supported interfaces instead of plain text.

---

## 📋 Status & Roadmap

| Feature / Capability | Status | Implementation Details |
|---|---|---|
| Card Catalog (CRUD & Query) | ✅ Implemented | Firestore (`cards` collection) via `list_cards`, `get_card`, `add_card`, `update_card` |
| Virtual Booster Packs | ✅ Implemented | Random sampling from Firestore catalog via `open_booster_pack` |
| External Creature Data | ✅ Implemented | Live data & sprite fetching via `lookup_external_creature` (PokéAPI) |
| Image Generation & Asset Storage | ✅ Implemented | `gemini-3.1-flash-lite-image` + Google Cloud Storage bucket |
| Cross-Session Memory | ✅ Implemented | Vertex AI Memory Bank (`PreloadMemoryTool` + callback) |
| Rich Display Components | ✅ Implemented | A2UI v0.8 JSON catalog rendering via callback |
| Interactive Card Battles / Damage Simulation | ⏳ Planned | Code sandbox for battle stat math and damage calculation (planned, not yet implemented) |
| Automated P2P Trade System | ⏳ Planned | Multi-user trade negotiation and deck valuation (planned, not yet implemented) |

---

## 🌐 Live Web Application & Deployment

- **🚀 Live Cloud Run Web UI**: [https://card-collector-frontend-689344436861.us-east1.run.app](https://card-collector-frontend-689344436861.us-east1.run.app)
- **🤖 Agent Runtime Endpoint**: `projects/689344436861/locations/us-east1/reasoningEngines/5848463976349827072`
- **💾 Vertex AI Memory Bank**: `projects/689344436861/locations/us-east1/reasoningEngines/3263679265215873024`
- **☁️ Cloud Storage Public Bucket**: `gs://snap-tcg-cards-b661fd`

---

## 🏗️ Architecture & Technology Stack

- **Reasoning Engine / LLM**: `gemini-2.5-flash` via Google ADK
- **Image Generation Model**: `gemini-3.1-flash-lite-image` (Vertex AI)
- **Framework**: Google Agent Development Kit (ADK) + `agents-cli`
- **Database**: Google Cloud Firestore (Native Mode)
- **Media Storage**: Google Cloud Storage (GCS)
- **Memory Service**: Vertex AI Reasoning Engine / Memory Bank
- **Protocol**: A2A (Agent-to-Agent) & A2UI v0.8
- **Web Frontend**: Custom responsive Dark TCG UI + FastAPI A2A Proxy on Google Cloud Run

---

## 🚀 Setup and Local Execution

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Cloud SDK (`gcloud`) with authenticated credentials:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  ```

### 1. Installation

Clone the repository and install dependencies using `uv` and `agents-cli`:

```bash
cd card-collector
uv sync
```

Or using `agents-cli`:

```bash
agents-cli install
```

### 2. Running Locally

#### Development Playground (ADK Web)
To launch the interactive ADK development interface with auto-reload:

```bash
agents-cli playground
```

#### FastAPI / A2A Server
To run the FastAPI backend server directly:

```bash
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Testing and Code Quality

Run tests:
```bash
uv run pytest tests/unit tests/integration
```

Run linter:
```bash
agents-cli lint
```

---

## 📦 Project Structure

```text
card-collector/
├── app/
│   ├── __init__.py
│   ├── agent.py               # Core ADK agent definition, tools, and callbacks
│   ├── a2ui_utils.py          # A2UI response formatting callback
│   ├── fast_api_app.py        # FastAPI server entrypoint
│   └── app_utils/             # A2A and Reasoning Engine adapters
├── tests/                     # Unit and integration test suites
├── agents-cli-manifest.yaml   # Agent manifest configuration
├── pyproject.toml             # Project dependencies and tool configurations
└── seed_firestore.py          # Script to populate initial card catalog in Firestore
```
