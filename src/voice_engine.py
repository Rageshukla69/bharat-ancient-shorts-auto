"""
Young Indian Male Hindi Voiceover (`hi-IN`) + Millisecond Word-Boundary Timestamp Engine (`src/voice_engine.py`).
Mapped directly to your Heroku / GitHub Secrets Config Vars:
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION` (e.g., `centralindia`)
- `AZURE_TTS_VOICE`:
  Defaults to `hi-IN-AaravNeural` — Microsoft Azure's #1 energetic, crisp Young Indian Male Hindi voice!
  Automatic Hindi Male fallback chain on Azure Speech:
  1. `hi-IN-AaravNeural` (Young Indian Male Hindi — Energetic & Modern Creator Tone)
  2. `hi-IN-RehaanNeural` (Expressive Young Adult Indian Male Hindi Storyteller)
  3. `hi-IN-KunalNeural` (Crisp Documentary Hindi Male Voice)
  4. `hi-IN-ArjunNeural` (Bold Hindi Male Narrator)
  5. `hi-IN-MadhurNeural` (Deep Epic Puranic/Historical Hindi Male — also built into free Edge TTS fallback)
  Note: If an old `en-US-*` or `en-IN-*` voice name is left in your secrets, this engine automatically
  overrides it to `hi-IN-AaravNeural` so your Indian channel always speaks fluent Hindi!
- `VOICE_SPEED_PERCENT` (default `4` -> `+4%` crisp viral Hindi documentary pace)
"""
import asyncio
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple
from xml.sax.saxutils import escape

DEFAULT_HINDI_YOUNG_VOICE = "hi-IN-AaravNeural"
EDGE_TTS_HINDI_FALLBACK = "hi-IN-MadhurNeural"

# Strip zero-width joiners/spaces and stray markdown/emoji characters before TTS synthesis
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad]")
_UNSAFE_TTS_RE = re.compile(r"[^\u0900-\u097Fa-zA-Z0-9\s.,!?:;\-–—'\"%/&()।॥]")


@dataclass
class WordTiming:
    word: str
    start_sec: float
    end_sec: float
    scene_id: int


def sanitize_hindi_narration(text: str) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    norm = _ZERO_WIDTH_RE.sub("", norm)
    norm = norm.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    norm = _UNSAFE_TTS_RE.sub("", norm)
    return re.sub(r"\s+", " ", norm).strip()


def get_audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


class VoiceEngine:
    def __init__(self):
        self.speech_key = os.getenv("AZURE_SPEECH_KEY", "").strip()
        self.speech_region = os.getenv("AZURE_SPEECH_REGION", "centralindia").strip()

        raw_voice = os.getenv("AZURE_TTS_VOICE", DEFAULT_HINDI_YOUNG_VOICE).strip()
        # Ensure we ALWAYS use a Hindi (`hi-IN-*`) voice even if an English voice was copied from the US repo
        if not raw_voice or not raw_voice.lower().startswith("hi-in"):
            print(
                f"[VoiceEngine] Overriding '{raw_voice}' -> '{DEFAULT_HINDI_YOUNG_VOICE}' (Young Indian Male Hindi Voice)"
            )
            self.voice = DEFAULT_HINDI_YOUNG_VOICE
        else:
            self.voice = raw_voice

        self.xml_lang = "hi-IN"

        raw_speed = os.getenv("VOICE_SPEED_PERCENT", "4").strip().replace("%", "").replace("+", "")
        try:
            self.speed_pct = int(float(raw_speed))
        except ValueError:
            self.speed_pct = 4

    def synthesize_scenes(
        self, scenes: List[dict], output_dir: Path
    ) -> Tuple[Path, List[WordTiming], List[dict]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        scene_audio_files = []
        all_word_timings: List[WordTiming] = []
        enriched_scenes = []
        current_offset = 0.0

        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)
            text = sanitize_hindi_narration(scene.get("narration", ""))
            scene_mp3 = output_dir / f"scene_{scene_id:02d}.mp3"

            words_with_rel_times = self._synthesize_single_clip(text, scene_mp3)
            clip_dur = get_audio_duration(scene_mp3)

            scene_words = []
            for w_text, w_start, w_end in words_with_rel_times:
                wt = WordTiming(
                    word=w_text,
                    start_sec=round(current_offset + w_start, 3),
                    end_sec=round(current_offset + w_end, 3),
                    scene_id=scene_id,
                )
                all_word_timings.append(wt)
                scene_words.append(asdict(wt))

            scene_copy = dict(scene)
            scene_copy["narration"] = text
            scene_copy["start_sec"] = round(current_offset, 3)
            scene_copy["duration_sec"] = round(clip_dur, 3)
            scene_copy["end_sec"] = round(current_offset + clip_dur, 3)
            scene_copy["audio_path"] = str(scene_mp3)
            scene_copy["words"] = scene_words
            enriched_scenes.append(scene_copy)

            scene_audio_files.append(scene_mp3)
            current_offset += clip_dur

        concat_list = output_dir / "audio_concat.txt"
        concat_list.write_text(
            "\n".join([f"file '{p.resolve()}'" for p in scene_audio_files]),
            encoding="utf-8",
        )
        master_vo = output_dir / "voiceover_master.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-ar",
                "44100",
                "-ac",
                "2",
                str(master_vo),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(
            f"[VoiceEngine] Synthesized {len(enriched_scenes)} Hindi scenes with '{self.voice}' "
            f"(+{self.speed_pct}% speed, {current_offset:.1f}s total, {len(all_word_timings)} synced Hindi words)."
        )
        return master_vo, all_word_timings, enriched_scenes

    def _synthesize_single_clip(
        self, text: str, out_mp3: Path
    ) -> List[Tuple[str, float, float]]:
        if self.speech_key and self.speech_region:
            candidate_voices = list(
                dict.fromkeys([
                    self.voice,
                    "hi-IN-AaravNeural",
                    "hi-IN-RehaanNeural",
                    "hi-IN-KunalNeural",
                    "hi-IN-ArjunNeural",
                    "hi-IN-MadhurNeural",
                ])
            )
            for v_name in candidate_voices:
                try:
                    return self._call_azure_speech_sdk(text, out_mp3, v_name)
                except Exception as exc:
                    print(f"[VoiceEngine] Azure Speech notice with '{v_name}' ({exc}); trying next Hindi male voice...")

        return asyncio.run(self._call_edge_tts_with_boundaries(text, out_mp3))

    def _call_azure_speech_sdk(
        self, text: str, out_mp3: Path, voice_name: str
    ) -> List[Tuple[str, float, float]]:
        import azure.cognitiveservices.speech as speechsdk

        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.speech_region)
        speech_config.speech_synthesis_voice_name = voice_name
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
        )
        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(out_mp3))
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        word_boundaries: List[Tuple[str, float, float]] = []

        def on_word(evt):
            start_s = evt.audio_offset / 10_000_000.0
            dur_s = evt.duration.total_seconds() if evt.duration else 0.22
            word_boundaries.append((evt.text, start_s, start_s + max(dur_s, 0.12)))

        synthesizer.synthesis_word_boundary.connect(on_word)

        sign = "+" if self.speed_pct >= 0 else ""
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="hi-IN">'
            f'<voice name="{voice_name}">'
            f'<prosody rate="{sign}{self.speed_pct}%">{escape(text)}</prosody>'
            f"</voice></speak>"
        )
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"Azure Speech synthesis failed for {voice_name}: {result.reason}")

        if not word_boundaries:
            dur = get_audio_duration(out_mp3)
            return self._estimate_proportional_word_timings(text, dur)
        return word_boundaries

    async def _call_edge_tts_with_boundaries(
        self, text: str, out_mp3: Path
    ) -> List[Tuple[str, float, float]]:
        import edge_tts

        sign = "+" if self.speed_pct >= 0 else ""
        communicate = edge_tts.Communicate(text, EDGE_TTS_HINDI_FALLBACK, rate=f"{sign}{self.speed_pct}%")
        word_boundaries: List[Tuple[str, float, float]] = []

        with open(out_mp3, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start_s = chunk["offset"] / 10_000_000.0
                    dur_s = chunk["duration"] / 10_000_000.0
                    word_boundaries.append((chunk["text"], start_s, start_s + max(dur_s, 0.12)))

        if not word_boundaries:
            dur = get_audio_duration(out_mp3)
            return self._estimate_proportional_word_timings(text, dur)
        return word_boundaries

    @staticmethod
    def _estimate_proportional_word_timings(
        text: str, total_duration: float
    ) -> List[Tuple[str, float, float]]:
        raw_words = [w for w in re.split(r"\s+", text.strip()) if w]
        if not raw_words:
            return []
        weights = []
        for w in raw_words:
            # Preserve Devanagari characters and vowel signs when estimating syllable weight
            clean_chars = re.sub(r"[,.;:!?।॥—–\-\"'\(\)\[\]]+", "", w)
            weight = max(len(clean_chars), 2)
            if w.endswith((",", ";", "—", "-")):
                weight += 2.5
            elif w.endswith((".", "!", "?", "।", "॥")):
                weight += 4.0
            weights.append(float(weight))

        total_weight = sum(weights)
        effective_dur = max(total_duration - 0.08, 0.2)
        cursor = 0.02
        timings = []
        for w, weight in zip(raw_words, weights):
            span = (weight / total_weight) * effective_dur
            timings.append((w, cursor, cursor + span))
            cursor += span
        return timings
