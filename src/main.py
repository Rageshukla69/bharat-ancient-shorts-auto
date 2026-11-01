"""
Main End-to-End Orchestrator for the Automated Bharat Ancient History, Hindu Mythology, Gods & Temple Wonders
Hindi YouTube Shorts Channel (`src/main.py` — v11.0 HeyGen HyperFrames Studio Pro + 10 MAI Images + 0.40 BGM + Human Storyteller Edition).
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
from hyperframes_composer import HyperFramesComposer
from youtube_uploader import upload_short_to_youtube


def _should_skip_backup_cron_slot() -> bool:
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


def _write_github_step_summary(
    topic: str,
    title: str,
    fetcher: MediaFetcher,
    video_id: str,
    rendered_via_hyperframes_cli: bool,
):
    engine_label = (
        "HeyGen HyperFrames CLI (`npx hyperframes render`)"
        if rendered_via_hyperframes_cli
        else "HyperFrames HTML Bundle + Hybrid FFmpeg Cinema Engine"
    )
    lines = [
        f"## 🕉️ Bharat Ancient History & Mythology Short Summary (v11.0 HyperFrames Studio Pro) — `{title}`",
        f"- **Topic**: {topic}",
        f"- **Render Engine**: {engine_label}",
        f"- **HyperFrames Composition Bundle**: `output/hyperframes_project/index.html` (`preview.html`, `DESIGN.md`)",
        f"- **AI Visuals (`MAI-Image-2.6-Flash`)**: `{fetcher.ai_images_used} / {fetcher.max_ai_images}`",
        f"- **Background Audio Volume**: `{os.getenv('BG_MUSIC_VOLUME', '0.40')}`",
        f"- **YouTube Video ID**: `{video_id}`",
    ]
    summary_md = "\n".join(lines) + "\n"
    print("\n" + "=" * 78)
    print(summary_md)
    print("=" * 78 + "\n")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as sf:
                sf.write(summary_md)
        except Exception as exc:
            print(f"[Pipeline] GITHUB_STEP_SUMMARY write notice: {exc}")


def run_pipeline():
    load_dotenv()
    if _should_skip_backup_cron_slot():
        return

    temp_dir = Path("temp")
    output_dir = Path("output")
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (Path("assets/sfx/interstellar_bgm.wav")).exists():
        generate_all_sfx()

    llm = FoundryLLMClient()
    custom_topic = os.getenv("CUSTOM_TOPIC", "").strip()
    topic = custom_topic if custom_topic else select_next_topic(llm_client=llm)

    # Step 1: Human-Storyteller Hindi Storyboard & Script via `FOUNDRY_TEXT_MODEL` (`gpt-6-luna`)
    storyboard = llm.generate_storyboard(topic)
    scenes = storyboard.get("scenes", [])
    if not scenes:
        raise RuntimeError("Storyboard contained no scenes.")

    # Step 2: Human Storytelling Indian Male Hindi Voiceover (`hi-IN-RehaanNeural`) + Sanitized Word Timings
    voice_engine = VoiceEngine()
    master_vo, word_timings, enriched_scenes = voice_engine.synthesize_scenes(
        scenes, temp_dir / "audio"
    )

    # Step 3: Fetch Up to 10 `MAI-Image-2.6-Flash` 9:16 Visuals + Verified Indian Heritage Photos
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
        scene["asset_kind"] = (
            fetcher.scene_audit_log[-1].get("kind", "AI RECONSTRUCTION")
            if getattr(fetcher, "scene_audit_log", None)
            else ("AI RECONSTRUCTION" if "_ai" in Path(asset_path).name else "ARCHIVAL IMAGE")
        )

    print(
        f"[Pipeline] Visuals ready (100% 9:16 1080x1920): used {fetcher.ai_images_used}/{fetcher.max_ai_images} MAI-Image credits "
        f"and {len(fetcher.used_urls)} verified Indian heritage photos."
    )

    # Step 4: Generate Hindi Devanagari Word-Synced Captions (.ass) & 0.40 BGM Master Audio Mix
    ass_path = output_dir / "subtitles.ass"
    generate_synced_ass_captions(word_timings, enriched_scenes, ass_path)

    composer = VideoComposer()
    mixed_audio_wav = temp_dir / "master_mix.wav"
    composer._build_master_audio_mix(master_vo, mixed_audio_wav, temp_dir)

    # Step 5: Build HeyGen HyperFrames v11.0 Project (`output/hyperframes_project/`) & Render MP4
    hf_composer = HyperFramesComposer(project_dir=output_dir / "hyperframes_project")
    hf_project_dir = hf_composer.build_project(
        topic=topic,
        title=storyboard.get("title", topic),
        scenes=enriched_scenes,
        word_timings=word_timings,
        master_audio_wav=mixed_audio_wav,
    )

    final_mp4 = output_dir / "final_short.mp4"
    rendered_via_hf_cli = hf_composer.try_cli_render(final_mp4)
    if not rendered_via_hf_cli:
        composer.render_short(enriched_scenes, master_vo, ass_path, final_mp4, temp_dir / "segments")

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "topic": topic,
                "title": storyboard.get("title"),
                "description": storyboard.get("description"),
                "render_engine": "hyperframes_cli" if rendered_via_hf_cli else "hyperframes_hybrid_ffmpeg",
                "hyperframes_project_dir": str(hf_project_dir),
                "ai_images_used": fetcher.ai_images_used,
                "max_ai_images_cap": fetcher.max_ai_images,
                "bg_music_volume": composer.bg_music_vol,
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

    _write_github_step_summary(
        topic, storyboard.get("title", topic), fetcher, video_id, rendered_via_hf_cli
    )

    if video_id != "dry_run_id":
        mark_topic_completed(topic, video_id=video_id, title=storyboard.get("title", topic))
    print(f"[Pipeline] Completed v11.0 HyperFrames Hindi Short run for topic: '{topic}' (video_id={video_id})")


if __name__ == "__main__":
    run_pipeline()
