"""
Microsoft Foundry LLM Client for the Hindi Ancient India, Hindu Mythology, Gods & Ancient Wonders Channel.
Mapped directly to your Heroku / GitHub Secrets Config Vars:
- `FOUNDRY_TEXT_ENDPOINT` (falls back to `FOUNDRY_ENDPOINT`)
- `FOUNDRY_TEXT_API_KEY` (falls back to `FOUNDRY_API_KEY`)
- `FOUNDRY_TEXT_MODEL` (defaults to `gpt-6-luna`)

100% Hindi (Devanagari) Narration & Captions + English Archival Search Queries:
- Writes `title`, `description`, `narration`, and `on_screen_callout` in gripping, goosebump-inducing
  **Hindi (Devanagari script: देवनागरी)** — styled like top Indian channels (*The Divine Tales*,
  *Rahasya Talk Show*, *HyperQuest Hindi*, *Project Shivoham*).
- Keeps `wikimedia_query`, `wikipedia_articles`, `required_visual_keywords`, and `image_prompt` in
  **English** so Wikipedia's REST API, Wikimedia Commons, and `MAI-Image-2.6-Flash` retrieve 100%
  accurate temple, deity, and historical visuals.
"""
import json
import os
import re
from typing import Any, Dict, List
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

SYSTEM_PROMPT = """You are an elite viral Hindi documentary director and "ShortGPT / MoneyPrinterTurbo" visual architect for 60-second YouTube Shorts on Ancient Indian History (प्राचीन भारत का इतिहास), Hindu Mythology (रामायण, महाभारत, पुराण), Gods (भगवान शिव, विष्णु, कृष्ण, हनुमान), and Ancient Temple Wonders (प्राचीन मंदिरों के रहस्य).

CRITICAL LANGUAGE RULES (HINDI NARRATION + ENGLISH SEARCH QUERIES):
1. `narration` (MUST BE IN CLEAN HINDI DEVANAGARI SCRIPT):
   - Write every scene's `narration` in powerful, natural, high-retention **Hindi (देवनागरी लिपि)** suitable for a young Indian male narrator (`hi-IN-AaravNeural` / `hi-IN-RehaanNeural`).
   - NEVER include emojis, markdown symbols (`*`, `#`, `_`, `~`), bullet symbols, or special characters inside `narration`. Use ONLY clean Hindi Devanagari words, standard numerals (`0-9`), and standard punctuation (`।`, `,`, `?`, `!`).
   - Use engaging, dramatic Hindi storytelling (e.g., "क्या आप जानते हैं कि एलोरा का कैलाश मंदिर नीचे से ऊपर नहीं, बल्कि पहाड़ को ऊपर से नीचे काटकर बनाया गया था?").
   - Every single scene MUST be 6 to 10 Hindi words (~2.2 to 3.3 seconds), totaling ~125 to 145 Hindi words across 16 to 18 rapid scenes so the total voiceover stays strictly between 46 and 55 seconds.
2. `on_screen_callout` (CLEAN HINDI DEVANAGARI BADGE):
   - Short 1-3 word punchy Hindi badge (e.g., `"एलोरा, 756 ईस्वी"`, `"4 लाख टन पत्थर"`, `"द्वारका का रहस्य"`, `"महाभारत काल"`). NEVER put emojis or special symbols inside `on_screen_callout`. Leave empty `""` on half the scenes.
3. `title` & `description`:
   - Write a viral Hindi + Hinglish YouTube Short `title` under 70 chars including `#shorts` (e.g., `"कैलाश मंदिर का अनसुलझा रहस्य! | Kailasa Temple Mystery #shorts"`).
   - Write `description` in Hindi with viral hashtags (`#shorts #bharat #hindumythology #ancientindia #sanatandharma #rahasya #indianhistory`).
4. `wikipedia_articles`, `required_visual_keywords`, `wikimedia_query`, and `image_prompt` (MUST BE IN ENGLISH):
   - `wikipedia_articles`: 3 to 5 exact, canonical English Wikipedia article titles (e.g., `["Kailasa temple, Ellora", "Ellora Caves", "Rashtrakuta Empire", "Shiva"]`).
   - `required_visual_keywords`: 8 to 12 lowercase English nouns that identify authentic imagery for this topic (e.g., `["kailasa", "ellora", "temple", "shiva", "monolith", "rock-cut", "rashtrakuta", "cave", "sculpture"]`).
   - `wikimedia_query`: Specific English archival search query (always include `"temple"`, `"sculpture"`, `"ancient India"`, `"Chola bronze"`, or `"Raja Ravi Varma"`).
   - `image_prompt`: Detailed English prompt for `MAI-Image-2.6-Flash` describing a majestic, reverent vertical 9:16 Indian mythological or historical scene.
5. SMART AI vs ARCHIVAL MIX (`prefer_media`):
   - Set `"prefer_media": "archival"` for real stone temples, caves, stepwells, sculptures, and archaeological ruins.
   - Set `"prefer_media": "ai_image"` for divine mythological moments, celestial weapons (Astras), gods in cosmic form, or lost ancient wonders (up to `MAX_AI_IMAGES_PER_SHORT`).

Return ONLY valid JSON matching this schema:
{
  "title": "कैलाश मंदिर का अनसुलझा रहस्य! | Kailasa Temple #shorts",
  "description": "एलोरा के कैलाश मंदिर का निर्माण प्राचीन भारतीय वास्तुकला का सबसे बड़ा चमत्कार है। #shorts #bharat #hindumythology #ancientindia #sanatandharma #rahasya",
  "tags": ["shorts", "bharat", "hindumythology", "indianhistory", "ancientindia", "sanatandharma", "rahasya", "templesofindia"],
  "is_space_or_science": false,
  "wikipedia_articles": ["Kailasa temple, Ellora", "Ellora Caves", "Rashtrakuta Empire"],
  "required_visual_keywords": ["kailasa", "ellora", "temple", "rock", "monolith", "shiva", "cave", "carving", "sculpture", "rashtrakuta"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "प्राचीन भारत में एक ऐसा मंदिर है जिसे पूरा पहाड़ काटकर बनाया गया था।",
      "wikimedia_query": "Kailasa temple Ellora monolithic rock cut architecture",
      "nasa_query": "",
      "wikipedia_article": "Kailasa temple, Ellora",
      "image_prompt": "Breathtaking cinematic vertical 9:16 photograph of the ancient Kailasa Temple at Ellora carved inside a massive basalt cliff, golden hour sunlight, epic documentary realism, no text",
      "pexels_query": "ancient indian temple",
      "prefer_media": "archival",
      "effect": "blur_snap_zoom_in",
      "on_screen_callout": "एलोरा, 756 ईस्वी"
    }
  ]
}
"""


class FoundryLLMClient:
    def __init__(self):
        self.endpoint = (
            os.getenv("FOUNDRY_TEXT_ENDPOINT")
            or os.getenv("FOUNDRY_ENDPOINT")
            or ""
        ).strip().rstrip("/")
        self.api_key = (
            os.getenv("FOUNDRY_TEXT_API_KEY")
            or os.getenv("FOUNDRY_API_KEY")
            or ""
        ).strip()
        self.model = (
            os.getenv("FOUNDRY_TEXT_MODEL")
            or os.getenv("FOUNDRY_LLM_MODEL")
            or "gpt-6-luna"
        ).strip()

    def _candidate_urls(self) -> List[str]:
        base = self.endpoint
        if "/chat/completions" in base:
            root = base.split("/models/")[0].split("/openai/")[0].split("/chat/completions")[0].rstrip("/")
            candidates = [base]
        else:
            root = base.split("/models")[0].split("/openai")[0].rstrip("/")
            candidates = []

        candidates.extend([
            f"{root}/openai/deployments/{self.model}/chat/completions?api-version=2024-12-01-preview",
            f"{root}/openai/deployments/{self.model}/chat/completions?api-version=2024-10-21",
            f"{root}/models/chat/completions?api-version=2024-05-01-preview",
            f"{root}/openai/v1/chat/completions",
            f"{root}/v1/chat/completions",
            f"{root}/chat/completions",
        ])
        return list(dict.fromkeys(candidates))

    def _call_chat_completions(self, messages: List[Dict[str, str]]) -> str:
        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "Missing FOUNDRY_TEXT_ENDPOINT / FOUNDRY_TEXT_API_KEY in GitHub Secrets."
            )

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

        payload_variants = [
            {"model": self.model, "messages": messages},
            {"messages": messages},
        ]

        last_err_detail = ""
        for url in self._candidate_urls():
            for payload in payload_variants:
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=90)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            if content:
                                return content
                    else:
                        last_err_detail = f"[{resp.status_code} on {url.split('//')[-1][:45]}]: {resp.text[:300]}"
                except Exception as exc:
                    last_err_detail = str(exc)

        raise RuntimeError(f"All Microsoft Foundry endpoint variants failed. Last response: {last_err_detail}")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=2, max=6))
    def generate_storyboard(self, topic: str) -> Dict[str, Any]:
        max_ai = int(os.getenv("MAX_AI_IMAGES_PER_SHORT", "3"))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Create a 60-second Hindi YouTube Short storyboard on: '{topic}'. "
                    "IMPORTANT: Write `narration`, `on_screen_callout`, `title`, and `description` in gripping HINDI (Devanagari script: देवनागरी), "
                    "with ZERO emojis or markdown symbols inside `narration` or `on_screen_callout`, "
                    "while keeping `wikipedia_articles`, `required_visual_keywords`, `wikimedia_query`, and `image_prompt` in English! "
                    "Ensure 16 to 18 fast-paced scenes, each 6 to 10 Hindi words (~135 Hindi words total so the audio stays under 55 seconds). "
                    f"Set `prefer_media` to 'ai_image' on the {max_ai} most divine/conceptual scenes and 'archival' on all real temple/monument/sculpture scenes. "
                    "Output ONLY valid JSON."
                ),
            },
        ]
        content = self._call_chat_completions(messages)
        match = re.search(r"\{[\s\S]*\}", content)
        raw_json = match.group(0) if match else content
        storyboard = json.loads(raw_json)
        storyboard["topic"] = topic
        print(
            f"[FoundryLLM] Generated Hindi Storyboard '{storyboard.get('title')}' "
            f"({len(storyboard.get('scenes', []))} scenes, max_ai={max_ai}) via {self.model}."
        )
        return storyboard

    def verify_archival_candidates(
        self, topic: str, candidates: List[Dict[str, str]]
    ) -> List[str]:
        if not candidates:
            return []
        try:
            compact = [
                {
                    "id": c["id"],
                    "title": c.get("title", "")[:90],
                    "desc": c.get("desc", "")[:120],
                }
                for c in candidates[:35]
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a strict Indian history & mythology visual fact-checker. Given a topic and a list of candidate images "
                        "(with id, title, desc), return a JSON object `{\"approved_ids\": [...]}` containing ONLY the IDs of images "
                        "that genuinely depict the ancient temple, monument, deity sculpture, Chola bronze, classical painting (e.g. Raja Ravi Varma), "
                        "archaeological site, or historical subject. "
                        "STRICTLY REJECT any modern Bollywood/Hollywood actors, cricketers, athletes, politicians, modern street selfies, "
                        "modern tourist signboards, or homonym traps."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Topic: {topic}\nCandidates: {json.dumps(compact)}\nReturn ONLY valid JSON: {{\"approved_ids\": [...]}}",
                },
            ]
            content = self._call_chat_completions(messages)
            match = re.search(r"\{[\s\S]*\}", content)
            data = json.loads(match.group(0) if match else content)
            approved = data.get("approved_ids", [])
            return [str(x) for x in approved]
        except Exception as exc:
            print(f"[FoundryLLM] Candidate verification fallback notice: {exc}")
            return [c["id"] for c in candidates]

    def generate_fresh_topic(self, recent_topics: List[str]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return ONLY a single line in English describing one fascinating, true Ancient Indian History, "
                    "Hindu Mythology (Ramayana, Mahabharata, Puranas), Sacred Deity Mystery (Shiva, Vishnu, Krishna, Hanuman, Devi), "
                    "or Ancient Indian Temple / Architectural Wonder topic suitable for a viral 60-second Hindi YouTube Short. "
                    "Do not repeat any topic from the provided list."
                ),
            },
            {
                "role": "user",
                "content": f"Suggest 1 brand-new Ancient India / Mythology / Temple Wonder topic not in this list: {', '.join(recent_topics[-50:])}",
            },
        ]
        content = self._call_chat_completions(messages)
        return content.strip().strip('"').strip("'")

    def generate_fresh_topics_batch(self, recent_topics: List[str], count: int = 15) -> List[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a viral Ancient Indian History, Hindu Mythology & Temple Wonders documentary producer. "
                    "Return ONLY a JSON array of strings in English (`[\"Topic 1\", \"Topic 2\", ...]`) containing fascinating, "
                    "true Ancient Indian History, Hindu Mythology (Ramayana, Mahabharata, Puranas), Gods, or Temple Wonder topics."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate {count} brand-new Ancient India / Mythology / Temple Wonder topics that do NOT overlap with any of these: "
                    f"{json.dumps(recent_topics[-60:])}. Return ONLY a valid JSON array of strings."
                ),
            },
        ]
        content = self._call_chat_completions(messages)
        match = re.search(r"\[[\s\S]*\]", content)
        arr = json.loads(match.group(0) if match else content)
        return [str(x).strip() for x in arr if str(x).strip()]
