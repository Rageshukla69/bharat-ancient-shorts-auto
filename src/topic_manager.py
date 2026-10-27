"""
Manages Ancient Indian History, Hindu Mythology, Gods & Temple Wonders topic selection (`src/topic_manager.py`).
- Starts with 60 curated high-retention topics in `data/topics_seed.json` (30 full days at 2 Shorts/day).
- NEVER stops after 60 topics: once the initial 60 seed topics are completed (or when fewer than 3 unused
  seed topics remain), it automatically calls `llm_client.generate_fresh_topic()` (`gpt-6-luna`) to invent
  brand-new, non-repeating Ancient India / Hindu Mythology / Sacred Temple Wonder topics AND appends them
  to `data/topics_seed.json` so your channel runs infinitely forever!
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SEED_FILE = Path("data/topics_seed.json")
USED_FILE = Path("data/used_topics.json")
HISTORY_FILE = Path("data/upload_history.json")

# Built-in reserve topics if LLM topic expansion is ever called offline
RESERVE_BHARAT_TOPICS = [
    "The Mystery of Karni Mata Temple and the 25,000 Sacred Rats of Deshnoke",
    "How Chhatrapati Shivaji Maharaj Engineered the Impregnable Raigad and Pratapgad Forts",
    "The Secret of Samudra Manthan: How the Devas and Asuras Churned the Cosmic Ocean",
    "Why the Shadow of Brihadeeswarar Temple's Vimana Mystifies Architects",
    "The Untold Story of Maharana Pratap and the Battle of Haldighati",
    "How Ancient Indian Astronomer Aryabhata Calculated Earth's Rotation and Pi",
    "The Mystery of the Underground Rooms Sealed Inside Padmanabhaswamy Temple",
    "How Lord Kartikeya Defeated Tarakasura as Commander of the Gods",
    "The Ancient Acoustic Engineering of Hampi's Vijaya Vittala Musical Pillars",
    "The Legend of Barbarika (Khatu Shyam Ji) and His Three Infallible Arrows in Mahabharata",
    "How the Chola Navy Built the Greatest Maritime Empire of Ancient Asia",
    "The Sacred Geometry of the Sri Yantra in Ancient Hindu Temple Architecture",
]


def load_used_topics() -> List[str]:
    if not USED_FILE.exists():
        return []
    try:
        data = json.loads(USED_FILE.read_text(encoding="utf-8"))
        return data.get("used", [])
    except Exception:
        return []


def load_seed_topics() -> List[str]:
    if not SEED_FILE.exists():
        return []
    try:
        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_seed_topics(seeds: List[str]) -> None:
    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(json.dumps(seeds, indent=2, ensure_ascii=False), encoding="utf-8")


def select_next_topic(llm_client=None) -> str:
    custom = os.getenv("CUSTOM_TOPIC", "").strip()
    if custom:
        print(f"[TopicManager] Using custom topic from workflow input: {custom}")
        return custom

    used_list = load_used_topics()
    used_set = set(used_list)
    seeds = load_seed_topics()

    unused_seeds = [t for t in seeds if t not in used_set]

    # Auto-replenish the seed bank when fewer than 3 unused topics remain so it NEVER runs out
    if len(unused_seeds) < 3 and llm_client is not None:
        try:
            fresh = llm_client.generate_fresh_topic(used_list + seeds)
            if fresh and fresh not in used_set and fresh not in seeds:
                seeds.append(fresh)
                save_seed_topics(seeds)
                unused_seeds.append(fresh)
                print(f"[TopicManager] Auto-replenished seed bank with new AI topic: {fresh}")
        except Exception as exc:
            print(f"[TopicManager] Auto-replenish notice: {exc}")

    if unused_seeds:
        chosen = unused_seeds[0]
        print(
            f"[TopicManager] Selected next unused topic ({len(unused_seeds)} remaining in queue): {chosen}"
        )
        return chosen

    # All 60+ seed topics used — generate a brand-new Ancient India / Mythology topic via GPT-6 Luna
    if llm_client is not None:
        print(
            "[TopicManager] All 60 seed topics completed! Generating fresh Ancient India / Mythology topic via GPT-6 Luna..."
        )
        try:
            fresh = llm_client.generate_fresh_topic(used_list[-60:])
            if fresh:
                if fresh not in seeds:
                    seeds.append(fresh)
                    save_seed_topics(seeds)
                return fresh
        except Exception as exc:
            print(f"[TopicManager] LLM topic generation fallback notice: {exc}")

    for reserve in RESERVE_BHARAT_TOPICS:
        if reserve not in used_set:
            seeds.append(reserve)
            save_seed_topics(seeds)
            return reserve

    return f"Untold Ancient Indian Temple & Puranic Mystery #{len(used_set) + 1}"


def mark_topic_completed(topic: str, video_id: Optional[str] = None, title: str = ""):
    USED_FILE.parent.mkdir(parents=True, exist_ok=True)
    used = load_used_topics()
    if topic not in used:
        used.append(topic)
    USED_FILE.write_text(json.dumps({"used": used}, indent=2, ensure_ascii=False), encoding="utf-8")

    uploads = []
    if HISTORY_FILE.exists():
        try:
            uploads = json.loads(HISTORY_FILE.read_text(encoding="utf-8")).get("uploads", [])
        except Exception:
            uploads = []

    uploads.append({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "title": title or topic,
        "youtube_video_id": video_id or "dry_run",
        "youtube_url": f"https://youtube.com/shorts/{video_id}" if video_id else None,
    })
    HISTORY_FILE.write_text(json.dumps({"uploads": uploads}, indent=2, ensure_ascii=False), encoding="utf-8")
