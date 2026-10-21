"""Unit tests for the Card Collector agent tools."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.agent import (
    list_cards,
    get_card,
    add_card,
    update_card,
    open_booster_pack,
    lookup_external_creature,
    generate_card_artwork,
)


def test_list_cards():
    with patch("app.agent._get_firestore_client") as mock_client:
        mock_db = MagicMock()
        mock_client.return_value = mock_db
        mock_doc = MagicMock()
        mock_doc.id = "card_001"
        mock_doc.to_dict.return_value = {"name": "Ignis Drake", "element": "Fire"}
        mock_db.collection.return_value.limit.return_value.stream.return_value = [mock_doc]

        result = list_cards(limit=1)
        assert len(result) == 1
        assert result[0]["name"] == "Ignis Drake"
        assert result[0]["id"] == "card_001"


def test_get_card():
    with patch("app.agent._get_firestore_client") as mock_client:
        mock_db = MagicMock()
        mock_client.return_value = mock_db
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.id = "card_001"
        mock_doc.to_dict.return_value = {"name": "Ignis Drake", "element": "Fire"}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        result = get_card("card_001")
        assert result["name"] == "Ignis Drake"
        assert result["id"] == "card_001"


def test_open_booster_pack():
    with patch("app.agent._get_firestore_client") as mock_client:
        mock_db = MagicMock()
        mock_client.return_value = mock_db
        mock_doc1 = MagicMock()
        mock_doc1.id = "c1"
        mock_doc1.to_dict.return_value = {"name": "Ignis Drake", "element": "Fire"}
        mock_doc2 = MagicMock()
        mock_doc2.id = "c2"
        mock_doc2.to_dict.return_value = {"name": "Aqua Siren", "element": "Water"}
        mock_doc3 = MagicMock()
        mock_doc3.id = "c3"
        mock_doc3.to_dict.return_value = {"name": "Terra Golem", "element": "Earth"}
        mock_db.collection.return_value.stream.return_value = [mock_doc1, mock_doc2, mock_doc3]

        pack = open_booster_pack("premium")
        assert pack["status"] == "success"
        assert pack["cards_drawn_count"] == 3
        assert len(pack["cards"]) == 3


def test_lookup_external_creature():
    result = lookup_external_creature("pikachu")
    assert result["status"] == "success"
    assert result["name"] == "Pikachu"
    assert "Electric" in result["elements"]
    assert "hp" in result
    assert "artwork_url" in result


@pytest.mark.asyncio
async def test_generate_card_artwork():
    with patch("app.agent.GenAIClient") as mock_genai_cls, patch("app.agent.storage.Client") as mock_storage_cls:
        # Mock GenAI response
        mock_genai_client = MagicMock()
        mock_genai_cls.return_value = mock_genai_client
        mock_part = MagicMock()
        mock_part.inline_data.data = b"fake_image_bytes"
        mock_part.inline_data.mime_type = "image/jpeg"
        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_genai_client.models.generate_content.return_value = mock_response

        # Mock Storage Client
        mock_storage_client = MagicMock()
        mock_storage_cls.return_value = mock_storage_client
        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Mock ToolContext
        mock_tool_context = MagicMock()
        mock_tool_context.save_artifact = AsyncMock()

        result = await generate_card_artwork("Solar Phoenix", "A majestic fire bird with glowing wings", mock_tool_context)
        assert result["status"] == "success"
        assert result["card_name"] == "Solar Phoenix"
        assert "https://storage.googleapis.com/snap-tcg-cards-b661fd/cards/solar_phoenix_" in result["public_url"]
        assert result["artifact_saved"] is True
        mock_tool_context.save_artifact.assert_called_once()
        mock_blob.upload_from_string.assert_called_once()



