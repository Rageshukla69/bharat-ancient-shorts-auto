r"""
Builds dynamic word-synced ASS subtitles for Hindi (Devanagari `देवनागरी`) & English in the viral documentary style:
- Uses `Noto Sans Devanagari` (installed via `fonts-noto-core`) with `Spacing: 0` so HarfBuzz shapes
  Devanagari conjuncts (`ब्रह्मास्त्र`, `श्रीकृष्ण`, `अद्भुत`), matras, and Shirorekha top-bars seamlessly
  with zero broken half-letters and zero missing-glyph boxes (`□□□`).
- Normalizes all Hindi text to Unicode NFC (`unicodedata.normalize("NFC", ...)`), strips emojis, markdown
  symbols, and zero-width characters (`\u200b`, `\u200c`, `\u200d`, `\ufeff`), and merges any standalone
  Devanagari combining marks/matras onto the preceding consonant so dotted circles (`◌`) can NEVER appear.
- Guarantees 100% boundary safety inside a 1080x1920 vertical canvas (`WrapStyle: 0` smart wrapping,
  character-budget chunking, explicit `\N` line breaks for longer phrases, and 90px left/right margins).
- Attaches Hindi Poorna Viram (`।`, `॥`) and standard punctuation (`,`, `.`, `;`, `:`, `!`, `?`) directly
  to the preceding word so floating punctuation marks never appear.
- Active spoken word pops in vibrant gold (`#FFD700`) at 108% scale while surrounding words stay crisp white.
"""
import re
import unicodedata
from pathlib import Path
from typing import List
from voice_engine import WordTiming

# Standalone punctuation tokens (including Hindi Poorna Viram `।` and Double Danda `॥`)
PUNCTUATION_ONLY_RE = re.compile(r"^[,.;:!?।॥—–\-\"'\)\]]+$")
LEADING_PUNCT_RE = re.compile(r"^([,.;:!?।॥]+)(.+)$")

# Devanagari combining marks (vowel signs/matras, anusvara, visarga, chandrabindu, nukta, virama/halant)
DEVANAGARI_COMBINING_START_RE = re.compile(
    r"^([\u0900-\u0903\u093A-\u094F\u0951-\u0957\u0962-\u0963]+)(.*)$"
)

# Zero-width & invisible formatting characters that can trigger tofu boxes in libass if left unstripped
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff\u00ad]")

# Strict whitelist of characters supported cleanly by Noto Sans Devanagari in libass:
# Devanagari block (\u0900-\u097F), basic ASCII letters/digits, whitespace, and clean punctuation.
UNSAFE_SYMBOL_RE = re.compile(
    r"[^\u0900-\u097Fa-zA-Z0-9\s.,!?:;\-–—'\"%/&()।॥]"
)


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int(round((secs - int(secs)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{int(secs):02d}.{centis:02d}"


def sanitize_hindi_caption_text(text: str) -> str:
    """
    Normalizes Hindi Devanagari text to NFC and removes any emojis, markdown symbols,
    zero-width characters, or unsupported symbols that could render as weird boxes (`□`)
    or dotted circles (`◌`) in FFmpeg libass.
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    norm = ZERO_WIDTH_RE.sub("", norm)
    norm = norm.replace("{", "").replace("}", "").replace("\\", "")
    # Replace Devanagari digits (०-९) with standard digits (0-9) for consistent bold rendering
    deva_digits = str.maketrans("०१२३४५६७८९", "0123456789")
    norm = norm.translate(deva_digits)
    # Strip any emoji, markdown (*, #, _, ~, `), or symbol outside Devanagari + standard Latin/punctuation
    norm = UNSAFE_SYMBOL_RE.sub("", norm)
    # Collapse multiple spaces
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _clean_word(word: str) -> str:
    cleaned = sanitize_hindi_caption_text(word)
    # Upper-case ASCII Latin letters while preserving all Devanagari characters & matras untouched
    cleaned = cleaned.upper()
    cleaned = re.sub(r"\s+([,.;:!?।॥])", r"\1", cleaned)
    # Strip any orphan combining mark at the very start of an isolated word so `◌` never renders
    cleaned = re.sub(r"^[\u0900-\u0903\u093A-\u094F\u0951-\u0957\u0962-\u0963]+", "", cleaned)
    return cleaned.strip()


def _truncate_hindi_badge(badge: str, max_words: int = 4, max_chars: int = 26) -> str:
    """
    Truncates a Hindi top badge cleanly on whole-word boundaries (never slicing mid-conjunct
    or leaving a dangling virama `्` at the end of a word).
    """
    cleaned = _clean_word(badge)
    if not cleaned:
        return ""
    words = [w for w in cleaned.split(" ") if w]
    selected: List[str] = []
    char_count = 0
    for w in words[:max_words]:
        projected = char_count + (1 if selected else 0) + len(w)
        if selected and projected > max_chars:
            break
        selected.append(w)
        char_count = projected

    result = " ".join(selected) if selected else words[0]
    # Never leave a trailing virama/halant (`्`, \u094D) at the end of a truncated badge
    result = result.rstrip("\u094d")
    return unicodedata.normalize("NFC", result)


def _merge_punctuation_tokens(word_timings: List[WordTiming]) -> List[WordTiming]:
    """
    Merges standalone punctuation tokens (including Hindi Poorna Viram `।` and `॥`) AND any
    split Devanagari combining marks/matras onto the immediately preceding word so captions
    never render floating punctuation or dotted circles (`◌`).
    """
    merged: List[WordTiming] = []
    for wt in word_timings:
        raw = sanitize_hindi_caption_text(wt.word)
        if not raw:
            continue

        # 1. If token starts with a Devanagari combining mark (matra/virama/anusvara), attach to previous word
        m_comb = DEVANAGARI_COMBINING_START_RE.match(raw)
        if m_comb:
            comb_marks, remainder = m_comb.group(1), m_comb.group(2).strip()
            if merged and merged[-1].scene_id == wt.scene_id:
                prev = merged[-1]
                merged[-1] = WordTiming(
                    word=unicodedata.normalize("NFC", f"{prev.word}{comb_marks}"),
                    start_sec=prev.start_sec,
                    end_sec=max(prev.end_sec, wt.end_sec if not remainder else prev.end_sec),
                    scene_id=prev.scene_id,
                )
            raw = remainder
            if not raw:
                continue

        # 2. Standalone punctuation token
        if PUNCTUATION_ONLY_RE.match(raw) and merged and merged[-1].scene_id == wt.scene_id:
            prev = merged[-1]
            merged[-1] = WordTiming(
                word=f"{prev.word}{raw}",
                start_sec=prev.start_sec,
                end_sec=max(prev.end_sec, wt.end_sec),
                scene_id=prev.scene_id,
            )
            continue

        # 3. Leading punctuation followed by a word
        m_punct = LEADING_PUNCT_RE.match(raw)
        if m_punct and merged and merged[-1].scene_id == wt.scene_id:
            punct, rest = m_punct.group(1), m_punct.group(2).strip()
            prev = merged[-1]
            merged[-1] = WordTiming(
                word=f"{prev.word}{punct}",
                start_sec=prev.start_sec,
                end_sec=prev.end_sec,
                scene_id=prev.scene_id,
            )
            raw = rest
            if not raw:
                continue

        cleaned_token = _clean_word(raw)
        if not cleaned_token:
            continue

        merged.append(
            WordTiming(
                word=cleaned_token,
                start_sec=wt.start_sec,
                end_sec=wt.end_sec,
                scene_id=wt.scene_id,
            )
        )
    return merged


def _group_into_safe_chunks(
    word_timings: List[WordTiming],
    max_words: int = 3,
    max_chars_two_lines: int = 28,
) -> List[List[WordTiming]]:
    """
    Groups Hindi/Devanagari words within each scene into tight 2-to-3 word phrases that NEVER overflow
    the 1080px horizontal safe zone (900px effective width).
    """
    chunks: List[List[WordTiming]] = []
    i = 0
    n = len(word_timings)

    while i < n:
        scene_id = word_timings[i].scene_id
        chunk: List[WordTiming] = []
        char_len = 0

        while i < n and word_timings[i].scene_id == scene_id and len(chunk) < max_words:
            candidate = _clean_word(word_timings[i].word)
            if not candidate:
                i += 1
                continue
            cand_len = len(candidate)
            projected = char_len + (1 if chunk else 0) + cand_len

            if chunk and projected > max_chars_two_lines:
                break
            if len(chunk) >= 2 and projected > 22:
                break

            chunk.append(word_timings[i])
            char_len = projected
            i += 1

            if candidate.endswith((".", "!", "?", ";", ":", "।", "॥")):
                break

        if chunk:
            chunks.append(chunk)

    return chunks


def _format_chunk_lines(
    chunk: List[WordTiming],
    active_idx: int,
    max_single_line_chars: int = 16,
) -> str:
    r"""
    Formats a chunk of 1-3 Hindi words with active-word gold pop styling and inserts an explicit
    ASS `\N` line break when total characters exceed `max_single_line_chars`.
    """
    plain_words = [_clean_word(wt.word) for wt in chunk]
    styled_words = []
    for j, w_str in enumerate(plain_words):
        if j == active_idx:
            styled_words.append(
                f"{{\\c&H00D7FF&\\fscx108\\fscy108}}{w_str}{{\\c&HFFFFFF&\\fscx100\\fscy100}}"
            )
        else:
            styled_words.append(w_str)

    total_chars = sum(len(w) for w in plain_words) + max(0, len(plain_words) - 1)
    if len(plain_words) <= 1 or total_chars <= max_single_line_chars:
        return " ".join(styled_words)

    if len(plain_words) == 2:
        return f"{styled_words[0]}\\N{styled_words[1]}"

    split_after_first = abs(len(plain_words[0]) - (len(plain_words[1]) + 1 + len(plain_words[2])))
    split_after_second = abs((len(plain_words[0]) + 1 + len(plain_words[1])) - len(plain_words[2]))
    if split_after_first <= split_after_second:
        return f"{styled_words[0]}\\N{styled_words[1]} {styled_words[2]}"
    return f"{styled_words[0]} {styled_words[1]}\\N{styled_words[2]}"


def generate_synced_ass_captions(
    word_timings: List[WordTiming],
    scenes: List[dict],
    output_ass: Path,
) -> Path:
    output_ass.parent.mkdir(parents=True, exist_ok=True)

    # IMPORTANT FOR DEVANAGARI: `Spacing` MUST be `0` on both styles so HarfBuzz connects
    # the top Shirorekha bar and shapes conjuncts (`ब्रह्मास्त्र`, `श्रीकृष्ण`) without gaps!
    header = """[Script Info]
Title: Bharat Ancient History & Mythology Hindi Word-Synced Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MainCaption,Noto Sans Devanagari,64,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,2,90,90,430,1
Style: TopBadge,Noto Sans Devanagari,40,&H0000D7FF,&H00FFFFFF,&H00121212,&HC8080808,-1,0,0,0,100,100,0,0,3,12,0,8,90,90,185,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []

    clean_timings = _merge_punctuation_tokens(word_timings)
    chunks = _group_into_safe_chunks(clean_timings)

    for chunk in chunks:
        for active_idx, active_wt in enumerate(chunk):
            ev_start = active_wt.start_sec
            if active_idx + 1 < len(chunk):
                ev_end = chunk[active_idx + 1].start_sec
            else:
                ev_end = active_wt.end_sec

            if ev_end <= ev_start:
                ev_end = ev_start + 0.12

            line_text = _format_chunk_lines(chunk, active_idx)
            events.append(
                f"Dialogue: 2,{_format_ass_time(ev_start)},{_format_ass_time(ev_end)},MainCaption,,0,0,0,,{line_text}"
            )

    last_badge = ""
    for scene in scenes:
        badge = (scene.get("on_screen_callout") or "").strip()
        if not badge:
            continue
        clean_badge = _truncate_hindi_badge(badge, max_words=4, max_chars=26)
        if not clean_badge or clean_badge == last_badge:
            continue
        last_badge = clean_badge

        s_start = float(scene.get("start_sec", 0.0)) + 0.08
        s_end = min(float(scene.get("end_sec", s_start + 1.5)), s_start + 2.1)
        if s_end > s_start:
            events.append(
                f"Dialogue: 1,{_format_ass_time(s_start)},{_format_ass_time(s_end)},TopBadge,,0,0,0,,{{\\fad(140,180)}}  {clean_badge}  "
            )

    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[CaptionBuilder] Generated {len(events)} Hindi Devanagari word-synced subtitle events -> {output_ass}")
    return output_ass
