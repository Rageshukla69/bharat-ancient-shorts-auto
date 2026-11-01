"""
Microsoft Foundry LLM Client for the Hindi Ancient India, Hindu Mythology, Gods & Ancient Wonders Channel
(`src/foundry_llm.py` — v11.0 Human Storyteller + HyperFrames Studio Pro + Up to 10 MAI-Image-2.6-Flash Edition).
Mapped directly to your Heroku / GitHub Secrets Config Vars:
- `FOUNDRY_TEXT_ENDPOINT` (falls back to `FOUNDRY_ENDPOINT`)
- `FOUNDRY_TEXT_API_KEY` (falls back to `FOUNDRY_API_KEY`)
- `FOUNDRY_TEXT_MODEL` (defaults to `gpt-6-luna`)

Key v11.0 Upgrades:
1. Warm, Human-Like Hindi Storytelling (`कहानीकार शैली`):
   - Writes `narration` in an intimate, goosebump-inducing human storyteller voice (like *The Divine Tales*, *Project Shivoham*, *HyperQuest Hindi*)
     using natural conversational bridges, rhetorical questions, and emotional pauses across **9 to 10 well-paced scenes** (115–140 Hindi words total).
2. Up to 10 Bespoke 9:16 `MAI-Image-2.6-Flash` Visuals per Short (`MAX_AI_IMAGES_PER_SHORT = 10` default):
   - Allocates up to 10 scenes to `prefer_media: "ai_image"` with hyper-detailed English cinema prompts so every scene renders a
     breathtaking 9:16 vertical Indian heritage / mythological visual.
3. Authors HyperFrames HUD Metadata (`on_screen_callout`, `stat_value`, `stat_label`, `era_tag`) in clean Hindi Devanagari.
"""
import json
import os
import re
from typing import Any, Dict, List
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

SYSTEM_PROMPT = """You are a master Hindi documentary storyteller (`कहानीकार`) and HyperFrames visual director for 60-second YouTube Shorts on Ancient Indian History (`प्राचीन भारत का इतिहास`), Hindu Mythology (`रामायण, महाभारत, पुराण`), Gods (`भगवान शिव, विष्णु, कृष्ण, हनुमान`), and Ancient Temple Wonders (`प्राचीन मंदिरों के रहस्य`).

CRITICAL LANGUAGE & HUMAN STORYTELLING RULES:
1. `narration` (WARM, HUMAN-LIKE HINDI DEVANAGARI STORYTELLING):
   - Write every scene's `narration` in warm, natural, conversational **Hindi (देवनागरी लिपि)** that sounds like a passionate human storyteller speaking directly to a friend — NOT a dry textbook or robotic newsreader.
   - Use natural human storytelling hooks and transitions (e.g., "जरा सोचिए...", "लेकिन सबसे चौंकाने वाली बात तो तब सामने आई, जब...", "कहते हैं कि...", "आज भी जब वैज्ञानिक इस रहस्य को देखते हैं, तो हैरान रह जाते हैं।").
   - Include natural commas (`,`), questions (`?`), and Poorna Viram (`।`) so the voice engine inserts real human breathing pauses.
   - NEVER include emojis, markdown symbols (`*`, `#`, `_`, `~`), or bullet symbols inside `narration`.
   - Structure the script into **9 to 10 scenes** (12 to 15 Hindi words per scene, ~120 to 140 Hindi words total) so each scene breathes for ~5 seconds and total duration is 48 to 56 seconds.
2. HYPERFRAMES HUD METADATA (CLEAN HINDI DEVANAGARI):
   - `on_screen_callout`: Short 2-4 word punchy Hindi badge (e.g., `"2,600 वर्ष पुरानी सर्जरी"`, `"4 लाख टन एकल चट्टान"`, `"द्वारका का समुद्री रहस्य"`).
   - `stat_value`: Optional numeric value when the scene mentions a year, age, weight, or count (e.g., `"2,600+"`, `"4,00,000"`, `"56"`, `"756"` or `""`).
   - `stat_label`: Short 1-3 word Hindi unit/label for `stat_value` (e.g., `"वर्ष पुराना"`, `"टन चट्टान"`, `"संगीतमय स्तंभ"`, `"ईस्वी निर्माण"`).
   - `era_tag`: Short Hindi era/location stamp (e.g., `"काशी // 600 ईसा पूर्व"`, `"एलोरा // राष्ट्रकूट काल"`, `"हम्पी // विजयनगर साम्राज्य"`).
3. `title` & `description`:
   - Write a viral Hindi + Hinglish YouTube Short `title` under 70 chars including `#shorts`.
   - Write `description` in Hindi with viral hashtags (`#shorts #bharat #hindumythology #ancientindia #sanatandharma #rahasya #indianhistory`).
4. `wikipedia_articles`, `required_visual_keywords`, `wikimedia_query`, and `image_prompt` (MUST BE IN ENGLISH):
   - `image_prompt`: Hyper-detailed English prompt for `MAI-Image-2.6-Flash` describing a photorealistic, reverent vertical 9:16 Indian mythological or historical cinema frame (golden temple oil lamps, sacred architecture, Chola bronze / stone carvings, dramatic chiaroscuro lighting, 35mm film grain, no text).
   - Set `"prefer_media": "ai_image"` across scenes (up to `MAX_AI_IMAGES_PER_SHORT = 10`) so every scene gets a bespoke 9:16 vertical visual.

Return ONLY valid JSON matching this schema:
{
  "title": "सुश्रुत संहिता: 2,600 साल पहले भारत में कैसे होती थी प्लास्टिक सर्जरी? #shorts",
  "description": "महर्षि सुश्रुत ने 2,600 वर्ष पहले काशी में मोतियाबिंद और राइनोप्लास्टी सर्जरी की विधि लिखी थी। #shorts #bharat #hindumythology #ancientindia #sanatandharma #rahasya",
  "tags": ["shorts", "bharat", "hindumythology", "indianhistory", "ancientindia", "sanatandharma", "rahasya", "templesofindia"],
  "is_space_or_science": false,
  "wikipedia_articles": ["Sushruta", "Sushruta Samhita", "History of plastic surgery"],
  "required_visual_keywords": ["sushruta", "ayurveda", "ancient", "india", "surgery", "manuscript", "temple", "statue"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "जरा सोचिए, आज से छब्बीस सौ साल पहले जब दुनिया में आधुनिक अस्पताल नहीं थे, तब भारत में जटिल सर्जरी हो रही थी।",
      "visual_subject": "Ancient Indian sage Sushruta examining bronze surgical instruments by oil lamp in Kashi",
      "wikimedia_query": "Sushruta statue ancient Indian physician surgeon",
      "nasa_query": "",
      "wikipedia_article": "Sushruta",
      "image_prompt": "Photorealistic vertical 9:16 cinema shot of ancient Indian sage Sushruta in classical Vedic robes inside a stone chamber in Kashi lit by warm brass oil lamps, examining finely crafted ancient bronze surgical instruments and palm-leaf manuscripts, dramatic lighting, 35mm film look, no text",
      "pexels_query": "ancient indian temple lamp",
      "prefer_media": "ai_image",
      "effect": "smooth_push_in",
      "on_screen_callout": "2,600 वर्ष पुरानी सर्जरी",
      "stat_value": "2,600+",
      "stat_label": "वर्ष पुराना विज्ञान",
      "era_tag": "काशी // 600 ईसा पूर्व"
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10))
    def generate_storyboard(self, topic: str) -> Dict[str, Any]:
        max_ai = max(0, int(os.getenv("MAX_AI_IMAGES_PER_SHORT", "10")))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Create a 50-56 second viral Hindi YouTube Short storyboard on this Ancient India / Hindu Mythology / Temple Wonder topic: '{topic}'. "
                    "Write all `narration` in warm, conversational, human-like Hindi (Devanagari script: देवनागरी) across 9 to 10 scenes "
                    "(12-15 Hindi words per scene, ~125-140 words total). "
                    f"Your `MAI-Image-2.6-Flash` budget is {max_ai} images per Short: set `prefer_media` to `\"ai_image\"` on up to {max_ai} scenes "
                    "with rich vertical 9:16 English `image_prompt` descriptions, and include Hindi `on_screen_callout`, `stat_value`, `stat_label`, and `era_tag` on each scene."
                ),
            },
        ]
        content = self._call_chat_completions(messages)
        match = re.search(r"\{[\s\S]*\}", content)
        storyboard = json.loads(match.group(0) if match else content)

        scenes = storyboard.get("scenes") or []
        if not isinstance(scenes, list) or not scenes:
            raise RuntimeError("Storyboard contained no scenes.")

        for idx, s in enumerate(scenes, 1):
            s["scene_id"] = int(s.get("scene_id") or idx)
            s["narration"] = str(s.get("narration") or "").strip()
            s["visual_subject"] = str(s.get("visual_subject") or s.get("wikimedia_query") or topic).strip()
            if s.get("prefer_media") not in {"ai_image", "archival", "video_clip"}:
                s["prefer_media"] = "ai_image" if max_ai >= 6 else "archival"

        # Promote scenes up to `min(max_ai, len(scenes))` so all 10 MAI-Image-2.6-Flash slots can be utilized
        current_ai = sum(1 for s in scenes if s.get("prefer_media") == "ai_image")
        if max_ai >= 1 and current_ai < min(max_ai, len(scenes)):
            priority_indices = [0, len(scenes) - 1, len(scenes) // 2, 1, len(scenes) - 2, 2, 3, 4, 5, 6, 7, 8, 9]
            for p_idx in priority_indices:
                if current_ai >= min(max_ai, len(scenes)):
                    break
                if 0 <= p_idx < len(scenes) and scenes[p_idx].get("prefer_media") != "ai_image":
                    scenes[p_idx]["prefer_media"] = "ai_image"
                    current_ai += 1

        ai_left = max_ai
        for s in scenes:
            if s.get("prefer_media") == "ai_image" and ai_left > 0:
                ai_left -= 1
            elif s.get("prefer_media") == "ai_image":
                s["prefer_media"] = "archival"

        print(
            f"[FoundryLLM] Generated Hindi Storyteller script '{storyboard.get('title')}' "
            f"with {len(scenes)} scenes (ai_image allocated={sum(1 for s in scenes if s.get('prefer_media') == 'ai_image')}/{max_ai})."
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
                        "You are an ultra-strict Indian heritage & mythology documentary photo editor. "
                        "Given `Topic` and candidate images (`id`, `title`, `desc`), return `{\"approved_ids\": [...]}` "
                        "containing ONLY the IDs of authentic photographs, classical Indian paintings (Raja Ravi Varma, Kangra, Tanjore, Pahari), "
                        "Chola bronzes, stone temple carvings, or archaeological ruins that directly depict `Topic`.\n"
                        "STRICTLY REJECT (return `[]` if none qualify):\n"
                        "- ANY modern celebrity, actor, singer, politician, cricketer, or sports player\n"
                        "- ANY red carpet, film festival, selfie, modern tourist snapshot, or modern street scene\n"
                        "- ANY flat schematic, diagram, chart, vector icon, coat of arms, or locator map."
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
            print(f"[FoundryLLM] Archival verification notice: {exc}")
            return [c["id"] for c in candidates]

    def generate_fresh_topic(self, recent_topics: List[str]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return ONLY a single line in English describing one fascinating Ancient Indian History, "
                    "Hindu Mythology (Mahabharata, Ramayana, Puranas), Gods (Shiva, Vishnu, Krishna, Hanuman), "
                    "or Ancient Indian Temple / Architectural Wonder topic suitable for a viral 60-second Hindi YouTube Short."
                ),
            },
            {
                "role": "user",
                "content": f"Suggest 1 new Ancient India / Mythology / Temple Wonder topic not in this list: {', '.join(recent_topics[-30:])}",
            },
        ]
        content = self._call_chat_completions(messages)
        return content.strip().strip('"')

    def generate_fresh_topics_batch(self, recent_topics: List[str], count: int = 15) -> List[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a viral Hindi documentary producer for an Ancient India, Hindu Mythology, Gods & Temple Wonders channel. "
                    "Return ONLY a JSON array of English strings (`[\"Topic 1\", \"Topic 2\", ...]`) containing fascinating "
                    "topics on Ancient Indian temples, Mahabharata/Ramayana secrets, Puranic stories of Shiva/Vishnu/Krishna/Hanuman, "
                    "and ancient Indian scientific/architectural marvels suitable for 60-second Hindi YouTube Shorts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate {count} brand-new, high-retention Ancient India & Hindu Mythology topics that do NOT overlap with any of these: "
                    f"{json.dumps(recent_topics[-60:])}. Return ONLY a valid JSON array of strings."
                ),
            },
        ]
        content = self._call_chat_completions(messages)
        match = re.search(r"\[[\s\S]*\]", content)
        arr = json.loads(match.group(0) if match else content)
        return [str(x).strip() for x in arr if str(x).strip()]
