"""Seed script for populating the card collector Firestore collection."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-b661fd22d876"
COLLECTION_NAME = "cards"

SAMPLE_CARDS = [
    {
        "id": "card_001",
        "name": "Ignis Drake",
        "element": "Fire",
        "rarity": "Legendary",
        "hp": 140,
        "attack": 95,
        "defense": 80,
        "speed": 110,
        "ability": "Flame Burst: Deals massive fire damage on first turn.",
        "description": "A legendary dragon born in volcanic flames, capable of scorching entire battlefields.",
        "price": 500,
        "in_stock": True,
    },
    {
        "id": "card_002",
        "name": "Aqua Siren",
        "element": "Water",
        "rarity": "Rare",
        "hp": 110,
        "attack": 75,
        "defense": 85,
        "speed": 90,
        "ability": "Tidal Wave: Heals allies and washes away status effects.",
        "description": "A mystical aquatic creature known to enchant sailors with soothing oceanic melodies.",
        "price": 250,
        "in_stock": True,
    },
    {
        "id": "card_003",
        "name": "Terra Golem",
        "element": "Earth",
        "rarity": "Uncommon",
        "hp": 160,
        "attack": 70,
        "defense": 120,
        "speed": 45,
        "ability": "Stone Wall: Reduces incoming physical damage by 30%.",
        "description": "Carved from ancient bedrock, this colossal guardian withstands even the heaviest blows.",
        "price": 150,
        "in_stock": True,
    },
    {
        "id": "card_004",
        "name": "Volt Kitsune",
        "element": "Electric",
        "rarity": "Epic",
        "hp": 95,
        "attack": 90,
        "defense": 60,
        "speed": 130,
        "ability": "Thunder Spark: High critical hit rate and speed priority.",
        "description": "A swift, nine-tailed electric fox that darts across storm clouds in the blink of an eye.",
        "price": 350,
        "in_stock": True,
    },
    {
        "id": "card_005",
        "name": "Shadow Wraith",
        "element": "Dark",
        "rarity": "Rare",
        "hp": 100,
        "attack": 85,
        "defense": 65,
        "speed": 105,
        "ability": "Night Veil: Evades attacks in low-light environments.",
        "description": "An elusive spirit wandering the twilight realm, striking from unexpected shadows.",
        "price": 220,
        "in_stock": True,
    },
    {
        "id": "card_006",
        "name": "Zephyr Falcon",
        "element": "Wind",
        "rarity": "Common",
        "hp": 80,
        "attack": 65,
        "defense": 55,
        "speed": 115,
        "ability": "Tailwind: Increases entire team's speed by 15%.",
        "description": "A keen-eyed bird of prey that glides through high mountain thermals.",
        "price": 80,
        "in_stock": True,
    },
    {
        "id": "card_007",
        "name": "Flora Pixie",
        "element": "Nature",
        "rarity": "Common",
        "hp": 75,
        "attack": 50,
        "defense": 60,
        "speed": 95,
        "ability": "Bloom Aroma: Slowly regenerates HP each turn.",
        "description": "A gentle forest fairy that nurtures rare enchanted wildflowers.",
        "price": 70,
        "in_stock": True,
    },
    {
        "id": "card_008",
        "name": "Cosmic Behemoth",
        "element": "Cosmic",
        "rarity": "Mythic",
        "hp": 200,
        "attack": 110,
        "defense": 100,
        "speed": 70,
        "ability": "Supernova: Emits a celestial explosion when HP drops below 25%.",
        "description": "An ancient entity that absorbed the stardust of collapsing galaxies.",
        "price": 1000,
        "in_stock": True,
    },
]


def seed_database():
    print(f"Connecting to Firestore with hardcoded project ID: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    print(f"Seeding {len(SAMPLE_CARDS)} cards into '{COLLECTION_NAME}' collection...")
    for card in SAMPLE_CARDS:
        doc_id = card["id"]
        collection_ref.document(doc_id).set(card)
        print(
            f"  ✓ Added card: {card['name']} ({card['rarity']} - {card['element']}) [ID: {doc_id}]"
        )

    print(f"\nSuccessfully seeded {len(SAMPLE_CARDS)} cards into Firestore!")


if __name__ == "__main__":
    seed_database()
