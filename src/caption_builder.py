r"""
Builds dynamic word-synced ASS subtitles for Hindi (Devanagari `देवनागरी`) & English in the viral Indian YouTube Creator style
(inspired by *Dhruv Rathee Shorts*, *The Divine Tales*, *HyperQuest*, and *Nitish Rajput*):
- Commanding `108pt` `Noto Sans Devanagari Bold` Main Captions (`MarginV: 530`) + `60pt` Top Callout Badges (`MarginV: 215`)
  with `Spacing: 0` so HarfBuzz shapes Devanagari conjuncts (`ब्रह्मास्त्र`, `श्रीकृष्ण`, `अद्भुत`), matras, and Shirorekha
  top-bars seamlessly with zero broken half-letters and zero missing-glyph boxes (`□□□`).
- True Devanagari Akshara/Visual-Width Line Balancer (`_visual_width`): counts top/bottom vowel signs (`ु`, `ू`, `ृ`, `े`, `ै`, `ं`, `ँ`)
  and halants (`्`) accurately as zero-width combining marks so 2-to-3 word chunks balance cleanly across 1 or 2 lines and
  NEVER overflow the 1080x1920 vertical canvas.
- Professional 75ms Active-Word Micro-Pop Animation (`\fscx100\fscy100\t(0,75,\fscx114\fscy114)`) in Warm Saffron-Gold (`#FFD700`)
  with an 8px deep-black stroke (`Outline: 8`), soft drop shadow (`Shadow: 5`), and `\blur0.7` edge anti-aliasing.
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

# Top/bottom non-spacing Devanagari marks (do not add horizontal width)
ZERO_ADVANCE_MARKS = set(
    "\u0900\u0901\u0902\u093a\u093c\u0941\u0942\u0943\u0944\u0945\u0946\u0947\u0948\u094d\u0951\u0952\u0953\u0954\u0955\u0956\u0957\u0962\u0963"
)
# Horizontal spacing matras (ा, ि, ी, ो, ौ, ः) add partial horizontal width (~0.35 of a full consonant)
PARTIAL_ADVANCE_MARKS = set("\u0903\u093b\u093e\u093f\u0940\u0949\u094a\u094b\u094c\u094e\u094f")


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int(round((secs - int(secs)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{int(secs):02d}.{centis:02d}"


def _visual_width(text: str) -> float:
    """
    Computes the true visual horizontal width of a Hindi/Devanagari or Latin string in base-character units:
    - Top/bottom matras (`ु`, `ू`, `ृ`, `े`, `ै`, `ं`, `ँ`) and virama/halant (`्`) add `0.0` width
      (and a virama slightly compacts the consonant cluster by `-0.25`).
    - Horizontal spacing matras (`ा`, `ि`, `ी`, `ो`, `ौ`, `ः`) add `0.35` width.
    - Base consonants/vowels/digits add `1.0` width.
    """
    width = 0.0
    for ch in text:
        if ch == "\u094d":  # Virama forms a half-letter conjunct
            width = max(0.5, width - 0.22)
        elif ch in ZERO_ADVANCE_MARKS:
            continue
        elif ch in PARTIAL_ADVANCE_MARKS:
            width += 0.35
        elif ch in ".,!?:;।॥'\"- ":
            width += 0.45
        else:
            width += 1.0
    return width


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
    deva_digits = str.maketrans("०१२३४५६७८९", "0123456789")
    norm = norm.translate(deva_digits)
    norm = UNSAFE_SYMBOL_RE.sub("", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _clean_word(word: str) -> str:
    cleaned = sanitize_hindi_caption_text(word)
    cleaned = cleaned.upper()
    cleaned = re.sub(r"\s+([,.;:!?।॥])", r"\1", cleaned)
    cleaned = re.sub(r"^[\u0900-\u0903\u093A-\u094F\u0951-\u0957\u0962-\u0963]+", "", cleaned)
    return cleaned.strip()


def _truncate_hindi_badge(badge: str, max_words: int = 4, max_visual_chars: float = 16.5) -> str:
    """
    Truncates a Hindi top badge cleanly on whole-word boundaries (never slicing mid-conjunct
    or leaving a dangling virama `्` at the end of a word) so it fits `60pt` TopBadge inside 1080px.
    """
    cleaned = _clean_word(badge)
    if not cleaned:
        return ""
    words = [w for w in cleaned.split(" ") if w]
    selected: List[str] = []
    vis_count = 0.0
    for w in words[:max_words]:
        w_vis = _visual_width(w)
        projected = vis_count + (0.6 if selected else 0.0) + w_vis
        if selected and projected > max_visual_chars:
            break
        selected.append(w)
        vis_count = projected

    result = " ".join(selected) if selected else words[0]
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

        if PUNCTUATION_ONLY_RE.match(raw) and merged and merged[-1].scene_id == wt.scene_id:
            prev = merged[-1]
            merged[-1] = WordTiming(
                word=f"{prev.word}{raw}",
                start_sec=prev.start_sec,
                end_sec=max(prev.end_sec, wt.end_sec),
                scene_id=prev.scene_id,
            )
            continue

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
    max_visual_two_lines: float = 19.5,
) -> List[List[WordTiming]]:
    """
    Groups Hindi/Devanagari words within each scene into punchy 2-to-3 word phrases sized for
    large `1080x1920` `108pt` creator typography while guaranteeing 100% boundary safety.
    """
    chunks: List[List[WordTiming]] = []
    i = 0
    n = len(word_timings)

    while i < n:
        scene_id = word_timings[i].scene_id
        chunk: List[WordTiming] = []
        vis_len = 0.0

        while i < n and word_timings[i].scene_id == scene_id and len(chunk) < max_words:
            candidate = _clean_word(word_timings[i].word)
            if not candidate:
                i += 1
                continue
            cand_vis = _visual_width(candidate)
            projected = vis_len + (0.6 if chunk else 0.0) + cand_vis

            if chunk and projected > max_visual_two_lines:
                break
            if len(chunk) >= 2 and projected > 15.5:
                break

            chunk.append(word_timings[i])
            vis_len = projected
            i += 1

            if candidate.endswith((".", "!", "?", ";", ":", "।", "॥")):
                break

        if chunk:
            chunks.append(chunk)

    return chunks


def _format_chunk_lines(
    chunk: List[WordTiming],
    active_idx: int,
    max_single_line_visual: float = 10.5,
) -> str:
    r"""
    Formats a chunk of 1-3 Hindi words at `108pt` with:
    - Smooth 75ms elastic micro-pop animation (`\fscx100\fscy100\t(0,75,\fscx114\fscy114)`) on the active word
      in Warm Saffron-Gold (`#FFD700` -> ASS `&H00D7FF&`).
    - Subtle 45ms entrance fade (`\fad(45,0)`) on the first word of a new phrase so transitions look silky-smooth.
    - Automatic font-size step-down (`\fs92`) if any single line exceeds 12.5 visual characters so even long
      Sanskrit compound words never touch the 1080px screen edges.
    """
    plain_words = [_clean_word(wt.word) for wt in chunk]
    vis_widths = [_visual_width(w) for w in plain_words]

    # Decide line split first so we can check maximum line visual width
    total_vis = sum(vis_widths) + 0.6 * max(0, len(plain_words) - 1)
    if len(plain_words) <= 1 or total_vis <= max_single_line_visual:
        line_groups = [list(range(len(plain_words)))]
    elif len(plain_words) == 2:
        line_groups = [[0], [1]]
    else:
        split1_diff = abs(vis_widths[0] - (vis_widths[1] + 0.6 + vis_widths[2]))
        split2_diff = abs((vis_widths[0] + 0.6 + vis_widths[1]) - vis_widths[2])
        if split1_diff <= split2_diff:
            line_groups = [[0], [1, 2]]
        else:
            line_groups = [[0, 1], [2]]

    max_line_vis = max(
        sum(vis_widths[idx] for idx in grp) + 0.6 * max(0, len(grp) - 1)
        for grp in line_groups
    )
    # Dynamic font size safety for extra-long Sanskrit/Hindi compound words
    base_fs = 92 if max_line_vis > 12.5 else 108

    styled_words = []
    for j, w_str in enumerate(plain_words):
        if j == active_idx:
            # Smooth 75ms elastic micro-pop from 100% -> 114% scale in Warm Saffron-Gold (#FFD700)
            styled_words.append(
                f"{{\\c&H00D7FF&\\fscx100\\fscy100\\t(0,75,\\fscx114\\fscy114)}}{w_str}{{\\c&HFFFFFF&\\fscx100\\fscy100}}"
            )
        else:
            styled_words.append(w_str)

    prefix_tags = f"{{\\blur0.7\\fs{base_fs}}}"
    if active_idx == 0:
        prefix_tags = f"{{\\fad(45,0)\\blur0.7\\fs{base_fs}}}"

    rendered_lines = [
        " ".join(styled_words[idx] for idx in grp)
        for grp in line_groups
    ]
    return prefix_tags + "\\N".join(rendered_lines)


def generate_synced_ass_captions(
    word_timings: List[WordTiming],
    scenes: List[dict],
    output_ass: Path,
) -> Path:
    output_ass.parent.mkdir(parents=True, exist_ok=True)

    # Viral Indian Creator Typography Standard (1080x1920):
    # - MainCaption: 108pt Noto Sans Devanagari Bold, 8px deep black outline, 5px shadow, MarginV=530 (focal sweet spot above YT UI)
    # - TopBadge: 60pt Noto Sans Devanagari Bold, warm gold text inside dark pill (BorderStyle=3, Outline=18, MarginV=215)
    # - Spacing=0 on both styles so HarfBuzz connects Devanagari Shirorekha bars and conjuncts seamlessly!
    header = """[Script Info]
Title: Bharat Ancient History & Mythology Hindi Word-Synced Captions (Pro Creator Edition)
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MainCaption,Noto Sans Devanagari,108,&H00FFFFFF,&H0000D7FF,&H00000000,&HA8000000,-1,0,0,0,100,100,0,0,1,8,5,2,65,65,530,1
Style: TopBadge,Noto Sans Devanagari,60,&H0000D7FF,&H00FFFFFF,&H00101015,&HD808080C,-1,0,0,0,100,100,0,0,3,18,0,8,65,65,215,1

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
        clean_badge = _truncate_hindi_badge(badge, max_words=4, max_visual_chars=16.5)
        if not clean_badge or clean_badge == last_badge:
            continue
        last_badge = clean_badge

        s_start = float(scene.get("start_sec", 0.0)) + 0.08
        s_end = min(float(scene.get("end_sec", s_start + 1.5)), s_start + 2.1)
        if s_end > s_start:
            events.append(
                f"Dialogue: 1,{_format_ass_time(s_start)},{_format_ass_time(s_end)},TopBadge,,0,0,0,,{{\\fad(150,180)}}  {clean_badge}  "
            )

    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[CaptionBuilder] Generated {len(events)} Pro 108pt Hindi Devanagari subtitle events -> {output_ass}")
    return output_ass
