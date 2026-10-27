# Autonomous Bharat Ancient History, Mythology, Gods & Temple Wonders — Hindi YouTube Shorts Engine (v4.0)

Built for your **Hindi YouTube Shorts Channel** covering **Ancient Indian History (प्राचीन भारत का इतिहास), Hindu Mythology (रामायण, महाभारत, पुराण), Gods & Divine Mysteries (भगवान शिव, विष्णु, कृष्ण, हनुमान), and Ancient Temple Architecture Wonders** (`Kailasa Temple Ellora`, `Konark Sun Temple`, `Brihadeeswarar Temple`, `Submerged Dwarka`, `Padmanabhaswamy Vault B`, `Vittala Musical Pillars`, `Sushruta Samhita`, `Nalanda`, `Lothal`, etc.).

## Key Features
1. **100% Hindi Narration & Captions with the Best Young Indian Male Voice (`hi-IN-AaravNeural`)**:
   - Pre-configured with Microsoft Azure's #1 energetic young Indian male Hindi voice (`hi-IN-AaravNeural`), with built-in fallback chain (`hi-IN-RehaanNeural` -> `hi-IN-KunalNeural` -> `hi-IN-ArjunNeural` -> `hi-IN-MadhurNeural`).
   - Even if an old English `en-US-*` or `en-IN-*` voice name is left in your GitHub Secrets, `src/voice_engine.py` automatically overrides it to `hi-IN-AaravNeural` so your channel always speaks fluent Hindi!
2. **Bold Devanagari Word-Synced Captions (`src/caption_builder.py`)**:
   - Renders Hindi (`देवनागरी`) word-by-word captions using `Noto Sans Devanagari Bold` with active-word gold pop (`#FFD700`), smart 1-to-2 line wrapping, and Poorna Viram (`।`) punctuation attachment.
3. **Bundled Custom Background Music (`assets/bgm/Dark cinema.mp3`) + Uplifting Interstellar Score**:
   - Includes your `assets/bgm/Dark cinema.mp3` track out of the box plus the synthesized uplifting organ & piano arpeggio score (`assets/sfx/interstellar_bgm.wav`), automatically ducked under the Hindi voiceover.
4. **3-Layer Indian Heritage Visual Verification (`src/media_fetcher.py`)**:
   - Queries Wikipedia's official REST Media-List API (`/api/rest_v1/page/media-list/{title}`) in English for canonical Indian temples, sculptures, Chola bronzes, Raja Ravi Varma paintings, and ASI monuments while narrating in Hindi.
