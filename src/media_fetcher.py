"""
Multi-Source Archival & Sacred Visual Engine for Ancient India, Mythology, Gods & Temple Wonders (`src/media_fetcher.py`):
1. Wikipedia Official REST Media-List API (`https://en.wikipedia.org/api/rest_v1/page/media-list/{title}`):
   Fetches ONLY the curated temple photographs, sculptures, Chola bronzes, classical paintings, and
   archaeological plates embedded inside the exact canonical Wikipedia articles for the topic.
2. 3-Layer Indian Heritage Verification Firewall:
   - Layer A: Hard Category & Celebrity Blacklist (rejects `Living people`, `Bollywood`, `Actors`, `Singers`,
     `Cricket`, `IPL`, `Baseball`, `Politicians`, `Film premieres`, `Red carpet`, `Tourist signboards`).
   - Layer B: Indian Heritage & Sacred Iconography Recognition (`ARCHIVAL_OVERRIDE_PATTERNS` recognizes
     temples across India are photographed in recent years by ASI/photographers while still blocking modern people/selfies).
   - Layer C: LLM Batch Candidate Verification (`llm_client.verify_archival_candidates`) via `gpt-6-luna`.
3. Reverent MAI-Image-2.6-Flash Generation (`MAX_AI_IMAGES_PER_SHORT`, default `3`):
   Generates majestic, high-detail vertical 9:16 Indian epic & mythological visuals within your credit cap.
"""
import base64
import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote
import requests
from PIL import Image, ImageEnhance, ImageFilter

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST_MEDIA = "https://en.wikipedia.org/api/rest_v1/page/media-list/"
WIKIPEDIA_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
NASA_IMAGES_API = "https://images-api.nasa.gov/search"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
USER_AGENT = "BharatAncientShortsBot/4.0 (https://github.com/education/students)"

DISQUALIFYING_PATTERNS = re.compile(
    r"\b("
    r"living people|births|actors|actresses|bollywood|hollywood|tollywood|kollywood|singers|musicians|rappers|"
    r"models|celebrities|jennifer lopez|bad bunny|benicio del toro|amaury nolasco|ana ortiz|prince harry|"
    r"shah rukh khan|salman khan|amitabh|deepika|priyanka|alia bhatt|ranbir|virat kohli|rohit sharma|dhoni|"
    r"red carpet|paparazzi|selfie|premiere|film festival|press conference|award|filmfare|iifa|grammy|oscar|"
    r"cricket|ipl|bcci|baseball|seattle mariners|burlington|football|basketball|soccer|hockey|athlete|player|"
    r"stadium|politician|minister|senator|election|rally|businesspeople|entrepreneur|ceo|"
    r"memorial plaque|information board|tourist sign|wayside marker|historical marker|commemorative plaque|"
    r"road sign|street sign|parking lot|shopping mall|headshot|portrait of a man|portrait of a woman|"
    r"logo|icon|coat of arms|flag of|map locator|blank map|svg|user:|talk:|template:"
    r")\b",
    re.IGNORECASE,
)

ARCHIVAL_OVERRIDE_PATTERNS = re.compile(
    r"\b("
    r"temple|mandapa|gopuram|shikhara|vimana|garbhagriha|stepwell|vav|cave|ellora|ajanta|konark|hampi|"
    r"brihadeeswarar|thanjavur|khajuraho|sanchi|nalanda|lothal|dholavira|mohenjo-daro|harappa|dwarka|"
    r"kailash|kailasa|kedarnath|badrinath|jagannath|puri|meenakshi|madurai|padmanabhaswamy|lepakshi|"
    r"modhera|belur|halebidu|hoysala|chola|maurya|gupta|pallava|rashtrakuta|vijayanagara|chalukya|"
    r"shiva|vishnu|krishna|rama|hanuman|ganesha|durga|kali|lakshmi|saraswati|brahma|indra|surya|nataraja|"
    r"narasimha|kalki|garuda|mahabharata|ramayana|kurukshetra|bhagavad gita|purana|veda|upanishad|"
    r"sushruta|aryabhata|chanakya|arthashastra|ashoka|iron pillar|golconda|bhangarh|kuldhara|"
    r"raja ravi varma|sculpture|relief|carving|bronze|murti|deity|statue|fresco|mural|manuscript|"
    r"inscription|pillar|monolith|archaeological|monument|museum|heritage|unesco"
    r")\b",
    re.IGNORECASE,
)

ABSOLUTE_REJECT_PATTERNS = re.compile(
    r"\b("
    r"living people|actors|actresses|bollywood|singers|musicians|rappers|cricket|ipl|baseball|seattle mariners|"
    r"red carpet|film premiere|movie premiere|television|filmfare|iifa|nbcuniversal|maxim|grammy|invictus games|"
    r"jennifer lopez|bad bunny|benicio del toro|amaury nolasco|ana ortiz|prince harry|"
    r"memorial plaque|wayside marker|information board|tourist sign|selfie"
    r")\b",
    re.IGNORECASE,
)


class MediaFetcher:
    def __init__(
        self,
        topic: str = "",
        era_keywords: Optional[List[str]] = None,
        wikipedia_articles: Optional[List[str]] = None,
        required_visual_keywords: Optional[List[str]] = None,
        is_space_or_science: bool = False,
        llm_client=None,
    ):
        self.foundry_endpoint = os.getenv("FOUNDRY_ENDPOINT", "").strip().rstrip("/")
        self.foundry_key = os.getenv("FOUNDRY_API_KEY", "").strip()
        self.image_model = os.getenv("FOUNDRY_IMAGE_MODEL", "MAI-Image-2.6-Flash").strip()
        self.pexels_key = os.getenv("PEXELS_API_KEY", "").strip()

        try:
            self.max_ai_images = max(0, int(os.getenv("MAX_AI_IMAGES_PER_SHORT", "3")))
        except ValueError:
            self.max_ai_images = 3
        self.ai_images_used = 0

        self.topic = topic
        self.era_keywords = era_keywords or []
        self.wikipedia_articles = wikipedia_articles or []
        self.required_keywords = [
            k.lower().strip() for k in (required_visual_keywords or []) if len(k.strip()) >= 3
        ]
        self.is_space_or_science = is_space_or_science
        self.llm_client = llm_client

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.attributions: List[str] = []

        self.used_urls: Set[str] = set()
        self.used_hashes: Set[str] = set()
        self.verified_pool: List[Dict[str, str]] = []
        self.downloaded_scene_images: List[Path] = []

        if self.topic:
            self._build_verified_archival_pool()

    def _has_domain_keyword_overlap(self, text: str) -> bool:
        low = text.lower()
        if self.required_keywords:
            return any(kw in low for kw in self.required_keywords)
        topic_nouns = [
            w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", self.topic)
            if w.lower() not in {"that", "with", "from", "into", "when", "what", "single", "missing", "almost", "most", "ancient"}
        ]
        return any(w in low for w in topic_nouns) if topic_nouns else True

    def _is_strictly_historical_and_relevant(
        self, title: str, desc: str, categories: str, width: int, height: int, trust_curated_source: bool = False
    ) -> bool:
        if width < 440 or height < 380:
            return False
        low_title = title.lower()
        if low_title.endswith((".svg", ".gif", ".tif", ".tiff", ".pdf", ".djvu", ".xcf", ".ogg", ".ogv", ".webm")):
            return False

        aspect = width / max(height, 1)
        if aspect > 2.5 or aspect < 0.35:
            return False

        combined = f"{title} {desc} {categories}"

        if ABSOLUTE_REJECT_PATTERNS.search(combined):
            return False

        if DISQUALIFYING_PATTERNS.search(combined):
            if not ARCHIVAL_OVERRIDE_PATTERNS.search(combined):
                return False

        if not trust_curated_source and not self._has_domain_keyword_overlap(combined):
            return False

        return True

    def _build_verified_archival_pool(self):
        raw_candidates: List[Dict[str, str]] = []

        articles_to_check = list(dict.fromkeys(self.wikipedia_articles[:5]))
        if not articles_to_check:
            articles_to_check = self._find_canonical_wikipedia_titles(self.topic)

        for article in articles_to_check:
            raw_candidates.extend(self._fetch_wikipedia_rest_article_media(article))

        for article in articles_to_check[:3]:
            raw_candidates.extend(self._search_wikimedia_candidates(f"{article} temple sculpture ancient India", limit=8))

        unique_candidates: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()
        for c in raw_candidates:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                c["id"] = f"img_{len(unique_candidates)}"
                unique_candidates.append(c)

        if self.llm_client and unique_candidates:
            approved_ids = set(self.llm_client.verify_archival_candidates(self.topic, unique_candidates))
            if approved_ids:
                self.verified_pool = [c for c in unique_candidates if c["id"] in approved_ids]
            else:
                self.verified_pool = unique_candidates
        else:
            self.verified_pool = unique_candidates

        print(
            f"[MediaFetcher] Built verified Indian heritage pool: {len(self.verified_pool)} approved images "
            f"(from {len(unique_candidates)} pre-filtered candidates) for '{self.topic}'."
        )

    def _find_canonical_wikipedia_titles(self, query: str) -> List[str]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        }
        try:
            resp = self.session.get(WIKIPEDIA_API, params=params, timeout=15)
            if resp.status_code == 200:
                hits = resp.json().get("query", {}).get("search", [])
                return [
                    h["title"] for h in hits
                    if not h["title"].lower().startswith("list of")
                    and not ABSOLUTE_REJECT_PATTERNS.search(h["title"])
                ]
        except Exception:
            pass
        return []

    def _fetch_wikipedia_rest_article_media(self, article_title: str) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        encoded = quote(article_title.replace(" ", "_"), safe="")
        try:
            sum_resp = self.session.get(f"{WIKIPEDIA_REST_SUMMARY}{encoded}", timeout=15)
            if sum_resp.status_code == 200:
                sdata = sum_resp.json()
                orig = sdata.get("originalimage", {}) or sdata.get("thumbnail", {})
                img_url = orig.get("source", "")
                w = int(orig.get("width", 1000))
                h = int(orig.get("height", 1000))
                desc = sdata.get("description", "") + " " + sdata.get("extract", "")
                if img_url and self._is_strictly_historical_and_relevant(
                    article_title, desc, article_title, w, h, trust_curated_source=True
                ):
                    results.append({
                        "url": img_url,
                        "title": f"{article_title} (Lead Archival Photo)",
                        "desc": desc[:160],
                        "license": "Wikipedia Archival",
                    })

            med_resp = self.session.get(f"{WIKIPEDIA_REST_MEDIA}{encoded}", timeout=15)
            if med_resp.status_code == 200:
                items = med_resp.json().get("items", [])
                for item in items:
                    if item.get("type") != "image":
                        continue
                    title = item.get("title", "").replace("File:", "")
                    caption = (item.get("caption", {}) or {}).get("text", "")
                    srcset = item.get("srcset", [])
                    if not srcset:
                        continue
                    best_src = srcset[-1].get("src", "")
                    if best_src.startswith("//"):
                        best_src = "https:" + best_src
                    if not best_src:
                        continue
                    if self._is_strictly_historical_and_relevant(
                        title, caption, article_title, 1000, 1000, trust_curated_source=True
                    ):
                        results.append({
                            "url": best_src,
                            "title": title,
                            "desc": f"{article_title}: {caption}"[:160],
                            "license": "Wikimedia Commons",
                        })
        except Exception as exc:
            print(f"[MediaFetcher] Wikipedia REST media-list notice for '{article_title}': {exc}")
        return results

    def _search_wikimedia_candidates(self, query: str, limit: int = 8) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|dimensions",
            "iiurlwidth": 1280,
            "format": "json",
        }
        try:
            resp = self.session.get(WIKIMEDIA_API, params=params, timeout=18)
            if resp.status_code != 200:
                return results
            pages = resp.json().get("query", {}).get("pages", {})
            sorted_pages = sorted(pages.values(), key=lambda p: p.get("index", 999))
            for page in sorted_pages:
                title = page.get("title", "").replace("File:", "")
                iinfo = (page.get("imageinfo") or [{}])[0]
                img_url = iinfo.get("thumburl") or iinfo.get("url")
                w = int(iinfo.get("width", 0))
                h = int(iinfo.get("height", 0))
                ext = iinfo.get("extmetadata", {}) or {}
                desc = str(ext.get("ImageDescription", {}).get("value", ""))
                cats = str(ext.get("Categories", {}).get("value", ""))
                date_orig = str(ext.get("DateTimeOriginal", {}).get("value", ""))

                if not img_url:
                    continue
                if not self._is_strictly_historical_and_relevant(
                    title, f"{desc} {date_orig}", cats, w, h, trust_curated_source=False
                ):
                    continue

                lic = ext.get("LicenseShortName", {}).get("value", "Public Domain / CC")
                results.append({
                    "url": img_url,
                    "title": title,
                    "desc": re.sub(r"<[^>]+>", "", desc)[:160],
                    "license": lic,
                })
        except Exception as exc:
            print(f"[MediaFetcher] Wikimedia candidate search notice for '{query}': {exc}")
        return results

    def fetch_scene_asset(
        self, scene: dict, assets_dir: Path
    ) -> Tuple[Path, str]:
        assets_dir.mkdir(parents=True, exist_ok=True)
        scene_id = int(scene.get("scene_id", 1))
        prefer = scene.get("prefer_media", "archival")
        wiki_q = scene.get("wikimedia_query", "")
        wp_article = scene.get("wikipedia_article", "")
        img_prompt = scene.get("image_prompt", "")
        pexels_q = scene.get("pexels_query", "")

        can_use_ai = (
            self.ai_images_used < self.max_ai_images
            and bool(self.foundry_endpoint and self.foundry_key)
        )

        if self.pexels_key and pexels_q and scene_id % 5 == 0:
            vid = self._fetch_pexels_video(pexels_q, assets_dir / f"scene_{scene_id:02d}.mp4")
            if vid:
                return vid, "video"

        if prefer == "ai_image" and can_use_ai and img_prompt:
            ai_img = self._generate_foundry_image(img_prompt, assets_dir / f"scene_{scene_id:02d}_ai.jpg")
            if ai_img:
                self.ai_images_used += 1
                self.downloaded_scene_images.append(ai_img)
                print(f"[MediaFetcher] Scene {scene_id:02d}: Generated MAI-Image ({self.ai_images_used}/{self.max_ai_images} budget)")
                return ai_img, "image"

        pool_img = self._pull_best_from_verified_pool(
            f"{wiki_q} {wp_article} {scene.get('narration', '')}",
            assets_dir / f"scene_{scene_id:02d}_archival.jpg",
        )
        if pool_img:
            self.downloaded_scene_images.append(pool_img)
            return pool_img, "image"

        if wp_article:
            for c in self._fetch_wikipedia_rest_article_media(wp_article):
                saved = self._download_and_register_image(
                    c["url"], assets_dir / f"scene_{scene_id:02d}_wp.jpg", c["title"], c["license"]
                )
                if saved:
                    self.downloaded_scene_images.append(saved)
                    return saved, "image"

        if wiki_q:
            for c in self._search_wikimedia_candidates(wiki_q, limit=6):
                saved = self._download_and_register_image(
                    c["url"], assets_dir / f"scene_{scene_id:02d}_wm.jpg", c["title"], c["license"]
                )
                if saved:
                    self.downloaded_scene_images.append(saved)
                    return saved, "image"

        if self.ai_images_used < self.max_ai_images and self.foundry_endpoint and self.foundry_key:
            prompt = img_prompt or f"Majestic ancient Indian temple architecture and sacred iconography of {wiki_q or self.topic}, golden hour lighting, vertical 9:16"
            ai_img = self._generate_foundry_image(prompt, assets_dir / f"scene_{scene_id:02d}_ai.jpg")
            if ai_img:
                self.ai_images_used += 1
                self.downloaded_scene_images.append(ai_img)
                print(f"[MediaFetcher] Scene {scene_id:02d}: Fallback MAI-Image ({self.ai_images_used}/{self.max_ai_images} budget)")
                return ai_img, "image"

        if self.downloaded_scene_images:
            source_img = self.downloaded_scene_images[(scene_id - 1) % len(self.downloaded_scene_images)]
            reframed_path = assets_dir / f"scene_{scene_id:02d}_detail.jpg"
            self._create_distinct_detail_crop(source_img, reframed_path, variant=scene_id)
            return reframed_path, "image"

        fallback_path = assets_dir / f"scene_{scene_id:02d}_fallback.jpg"
        self._create_archival_fallback_card(fallback_path)
        return fallback_path, "image"

    def _pull_best_from_verified_pool(self, scene_context: str, dest_path: Path) -> Optional[Path]:
        context_words = {
            w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", scene_context)
        }
        unused = [c for c in self.verified_pool if c["url"] not in self.used_urls]
        if not unused:
            return None

        def score_cand(c: Dict[str, str]) -> int:
            text = f"{c.get('title', '')} {c.get('desc', '')}".lower()
            return sum(1 for w in context_words if w in text)

        ranked = sorted(unused, key=score_cand, reverse=True)
        for cand in ranked:
            saved = self._download_and_register_image(
                cand["url"], dest_path, cand.get("title", ""), cand.get("license", "Public Domain")
            )
            if saved:
                return saved
        return None

    def _download_and_register_image(
        self, img_url: str, dest_path: Path, title: str = "", license_name: str = "Public Domain / CC"
    ) -> Optional[Path]:
        if img_url in self.used_urls:
            return None
        try:
            img_resp = self.session.get(img_url, timeout=25)
            img_resp.raise_for_status()
            content_bytes = img_resp.content
            digest = hashlib.md5(content_bytes).hexdigest()
            if digest in self.used_hashes:
                return None

            dest_path.write_bytes(content_bytes)
            with Image.open(dest_path) as im:
                w, h = im.size
                if w < 420 or h < 360:
                    dest_path.unlink(missing_ok=True)
                    return None
                im.convert("RGB").save(dest_path, quality=92)

            self.used_urls.add(img_url)
            self.used_hashes.add(digest)
            if title:
                clean_title = title.replace("File:", "")
                self.attributions.append(f"• {clean_title} ({license_name})")
            return dest_path
        except Exception:
            return None

    def _generate_foundry_image(self, prompt: str, dest_path: Path) -> Optional[Path]:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.foundry_endpoint)
            if parsed.scheme and parsed.netloc:
                resource_root = f"{parsed.scheme}://{parsed.netloc}"
            else:
                resource_root = self.foundry_endpoint.split("/api/projects")[0].split("/openai")[0].split("/models")[0].rstrip("/")

            headers = {
                "Content-Type": "application/json",
                "api-key": self.foundry_key,
                "Authorization": f"Bearer {self.foundry_key}",
            }
            clean_prompt = (
                f"{prompt}, majestic ancient Indian temple & epic documentary cinematography, golden temple oil lamp lighting, "
                "35mm film look, vertical 9:16 composition, no text, no watermarks, no modern elements"
            )

            route_attempts = [
                (
                    f"{resource_root}/mai/v1/images/generations",
                    {"model": self.image_model, "prompt": clean_prompt, "width": 768, "height": 1344},
                ),
                (
                    f"{resource_root}/openai/v1/images/generations",
                    {"model": self.image_model, "prompt": clean_prompt, "n": 1, "size": "1024x1792"},
                ),
                (
                    f"{resource_root}/openai/deployments/{self.image_model}/images/generations?api-version=2025-04-01-preview",
                    {"prompt": clean_prompt, "n": 1, "size": "1024x1792"},
                ),
            ]

            for url, payload in route_attempts:
                resp = requests.post(url, headers=headers, json=payload, timeout=55)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    if items and "b64_json" in items[0]:
                        dest_path.write_bytes(base64.b64decode(items[0]["b64_json"]))
                    elif items and "url" in items[0]:
                        img_r = self.session.get(items[0]["url"], timeout=35)
                        img_r.raise_for_status()
                        dest_path.write_bytes(img_r.content)
                    else:
                        continue
                    with Image.open(dest_path) as im:
                        im.convert("RGB").save(dest_path, quality=92)
                    return dest_path
            return None
        except Exception as exc:
            print(f"[MediaFetcher] Foundry {self.image_model} notice: {exc}")
            return None

    def _fetch_pexels_video(self, query: str, dest_path: Path) -> Optional[Path]:
        headers = {"Authorization": self.pexels_key}
        params = {"query": query, "orientation": "portrait", "per_page": 4, "size": "medium"}
        try:
            resp = self.session.get(PEXELS_VIDEO_API, headers=headers, params=params, timeout=20)
            resp.raise_for_status()
            for v in resp.json().get("videos", []):
                files = v.get("video_files", [])
                mp4s = [f for f in files if f.get("file_type") == "video/mp4" and f.get("height", 0) >= 720]
                if not mp4s:
                    continue
                chosen = sorted(mp4s, key=lambda x: abs(x.get("height", 0) - 1280))[0]
                vid_resp = self.session.get(chosen["link"], timeout=35)
                vid_resp.raise_for_status()
                dest_path.write_bytes(vid_resp.content)
                return dest_path
        except Exception:
            pass
        return None

    @staticmethod
    def _create_distinct_detail_crop(source_path: Path, dest_path: Path, variant: int = 1):
        with Image.open(source_path) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            crop_w = int(w * 0.72)
            crop_h = int(h * 0.72)
            offsets = [
                (int(w * 0.04), int(h * 0.06)),
                (int(w * 0.22), int(h * 0.10)),
                (int(w * 0.14), int(h * 0.20)),
                (int(w * 0.18), int(h * 0.04)),
            ]
            ox, oy = offsets[variant % len(offsets)]
            cropped = rgb.crop((ox, oy, min(w, ox + crop_w), min(h, oy + crop_h)))
            cropped = ImageEnhance.Contrast(cropped).enhance(1.10)
            cropped = ImageEnhance.Color(cropped).enhance(0.90)
            cropped.save(dest_path, quality=92)

    @staticmethod
    def _create_archival_fallback_card(dest_path: Path):
        w, h = 1080, 1920
        arr = Image.effect_noise((w, h), 28).convert("RGB")
        r, g, b = arr.split()
        r = r.point(lambda i: int(i * 0.28 + 26))
        g = g.point(lambda i: int(i * 0.22 + 18))
        b = b.point(lambda i: int(i * 0.14 + 12))
        img = Image.merge("RGB", (r, g, b)).filter(ImageFilter.GaussianBlur(radius=2))
        img.save(dest_path, quality=92)
