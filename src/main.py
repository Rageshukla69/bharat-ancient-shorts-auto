"""
Main End-to-End Orchestrator for the Automated Bharat Ancient History, Hindu Mythology, Gods & Temple Wonders
Hindi YouTube Shorts Channel (v4.2 — Strict 9:16 Full-Bleed & Reliable 12-Hour Scheduler Edition).
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from sfx_generator import generate_all_sfx
from topic_manager import select_next_topic, mark_topic_completed, HISTORY_FILE
from foundry_llm import FoundryLLMClient
from voice_engine import VoiceEngine
from media_fetcher import MediaFetcher
from caption_builder import generate_synced_ass_captions
from video_composer import VideoComposer
from youtube_uploader import upload_short_to_youtube


def _should_skip_backup_cron_slot() -> bool:
    """
    When triggered automatically by GitHub Actions `schedule` (which includes primary 12h slots + backup
    catch-up slots 3 hours later in case GitHub delays a cron run), checks if a Short was already uploaded
    within the last `min_hours_between` hours (default 9.5h for 2 Shorts/day).
    Manual `workflow_dispatch` runs NEVER skip!
    """
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    if event_name != "schedule":
        return False

    try:
        shorts_per_day = max(1, int(os.getenv("SHORTS_PER_DAY", "2")))
    except ValueError:
        shorts_per_day = 2
    min_hours_between = max(2.0, (24.0 / shorts_per_day) - 2.5)

    if not HISTORY_FILE.exists():
        return False
    try:
        uploads = json.loads(HISTORY_FILE.read_text(encoding="utf-8")).get("uploads", [])
        if not uploads:
            return False
        last_ts_str = uploads[-1].get("timestamp_utc", "")
        if not last_ts_str:
            return False
        last_dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        elapsed_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600.0
        if elapsed_hours < min_hours_between:
            print(
                f"[SchedulerGuard] Last Short was uploaded {elapsed_hours:.1f}h ago "
                f"(< {min_hours_between:.1f}h target window). Backup cron slot not needed — exiting cleanly."
            )
            return True
    except Exception as exc:
        print(f"[SchedulerGuard] History check notice: {exc}")
    return False


def run_pipeline():
    load_dotenv()
    if _should_skip_backup_cron_slot():
        return

    temp_dir = Path("temp")
    output_dir = Path("output")
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Always ensure the uplifting Interstellar documentary score exists as fallback
    if not (Path("assets/sfx/interstellar_bgm.wav")).exists():
        generate_all_sfx()

    llm = FoundryLLMClient()
    topic = select_next_topic(llm_client=llm)

    # Step 1: Hindi Storyboard & Script via `FOUNDRY_TEXT_MODEL` (`gpt-6-luna`)
    storyboard = llm.generate_storyboard(topic)
    scenes = storyboard.get("scenes", [])
    if not scenes:
        raise RuntimeError("Storyboard contained no scenes.")

    # Step 2: Young Indian Male Hindi Voiceover (`hi-IN-AaravNeural`) + Word Timings
    voice_engine = VoiceEngine()
    master_vo, word_timings, enriched_scenes = voice_engine.synthesize_scenes(
        scenes, temp_dir / "audio"
    )

    # Step 3: Fetch Verified 9:16 Indian Heritage Photos + Capped `MAI-Image-2.6-Flash`
    fetcher = MediaFetcher(
        topic=topic,
        era_keywords=storyboard.get("historical_era_keywords", []),
        wikipedia_articles=storyboard.get("wikipedia_articles", []),
        required_visual_keywords=storyboard.get("required_visual_keywords", []),
        is_space_or_science=bool(storyboard.get("is_space_or_science", False)),
        llm_client=llm,
    )
    for scene in enriched_scenes:
        asset_path, asset_type = fetcher.fetch_scene_asset(scene, temp_dir / "media")
        scene["asset_path"] = str(asset_path)
        scene["asset_type"] = asset_type

    print(
        f"[Pipeline] Visuals ready (100% 9:16 1080x1920): used {fetcher.ai_images_used}/{fetcher.max_ai_images} MAI-Image credits "
        f"and {len(fetcher.used_urls)} verified Indian heritage photos."
    )

    # Step 4: Generate Boundary-Safe Hindi Devanagari Word-Synced Captions (.ass)
    ass_path = output_dir / "subtitles.ass"
    generate_synced_ass_captions(word_timings, enriched_scenes, ass_path)

    # Step 5: Render 1080x1920 MP4 with Strict 9:16 Full-Bleed Framing & BGM Ducking
    composer = VideoComposer()
    final_mp4 = output_dir / "final_short.mp4"
    composer.render_short(enriched_scenes, master_vo, ass_path, final_mp4, temp_dir / "segments")

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "topic": topic,
                "title": storyboard.get("title"),
                "description": storyboard.get("description"),
                "ai_images_used": fetcher.ai_images_used,
                "max_ai_images_cap": fetcher.max_ai_images,
                "verified_pool_size": len(fetcher.verified_pool),
                "scenes": enriched_scenes,
                "attributions": fetcher.attributions,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Step 6: Upload to YouTube via `YOUTUBE_TOKEN_JSON` (skipped automatically when DRY_RUN=true)
    video_id = upload_short_to_youtube(
        video_path=final_mp4,
        title=storyboard.get("title", topic),
        description=storyboard.get("description", topic),
        tags=storyboard.get(
            "tags",
            ["shorts", "bharat", "hindumythology", "ancientindia", "sanatandharma", "indianhistory"],
        ),
        attributions=fetcher.attributions,
    )

    # Step 7: Only mark topic as used if not in dry_run mode
    if video_id != "dry_run_id":
        mark_topic_completed(topic, video_id=video_id, title=storyboard.get("title", topic))
    print(f"[Pipeline] Completed Hindi Short run for topic: '{topic}' (video_id={video_id})")


if __name__ == "__main__":
    run_pipeline()
