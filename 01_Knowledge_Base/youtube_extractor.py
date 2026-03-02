"""
🎬 YouTube Transcript Extractor
Parcourt les chaînes YouTube (Azure, AWS, GCP)
→ Extrait les transcripts des vidéos récentes
→ Les envoie au modèle Azure OpenAI pour structuration en .md
→ Sauvegarde dans data/processed/azure/, data/processed/aws/, data/processed/gcp/
"""
import os
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
import scrapetube

from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

# ─────────────────────────────────────
# 📍 Chemins — relatifs au script
# ─────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
CHANNELS_FILE = os.path.join(SCRIPT_DIR, "youtube_channels.json")

# Chercher le .env : dans le dossier du script OU le dossier parent
env_path = os.path.join(SCRIPT_DIR, ".env")
if not os.path.exists(env_path):
    env_path = os.path.join(SCRIPT_DIR, "..", ".env")
if not os.path.exists(env_path):
    env_path = os.path.join(SCRIPT_DIR, "..", "00_Config", ".env")

load_dotenv(env_path)

# ─────────────────────────────────────
# 🔑 Azure OpenAI
# ─────────────────────────────────────
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

client = AsyncAzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-02-01",
)

# ─────────────────────────────────────
# 🌐 Configuration Proxy (pour contourner le blocage YouTube sur IP cloud)
# ─────────────────────────────────────
# Formats supportés dans .env :
#   PROXY_URL=http://user:pass@proxy.example.com:8080
#   PROXY_URL=socks5://user:pass@proxy.example.com:1080
# ─────────────────────────────────────
PROXY_URL = os.getenv("PROXY_URL")

def create_ytt_client() -> YouTubeTranscriptApi:
    """Crée un client YouTubeTranscriptApi avec ou sans proxy."""
    if PROXY_URL:
        proxy_config = GenericProxyConfig(
            http_url=PROXY_URL,
            https_url=PROXY_URL,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)
    else:
        return YouTubeTranscriptApi()

# ─────────────────────────────────────
# 📝 Logging
# ─────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
log_file = os.path.join(LOGS_DIR, f"youtube_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────
# ⏰ Filtre de date
# ─────────────────────────────────────
MAX_AGE_MONTHS = 24
CUTOFF_DATE = datetime.now() - timedelta(days=MAX_AGE_MONTHS * 30)

# ─────────────────────────────────────
# 📺 Chaînes YouTube fiables (par défaut)
# ─────────────────────────────────────
DEFAULT_CHANNELS = {
    "azure": [
        {"id": "UCsMica-v34Irf9KVTh6xx-g", "name": "Microsoft Azure"},
        {"id": "UCpIn7ox7j7bH_OFj7tYouOQ", "name": "John Savill"},
        {"id": "UCdmEIMC3LBil4o0tjaTbj0w", "name": "Adam Marczak"},
    ],
    "aws": [
        {"id": "UCd6MoB9NC6uYN2grvUNT-Zg", "name": "Amazon Web Services"},
        {"id": "UCWN3xxRkmTPphA17mOOXqPw", "name": "Stephane Maarek"},
        {"id": "UCraiFqWi0qSIxXxXN4IHFBQ", "name": "Be A Better Dev"},
    ],
    "gcp": [
        {"id": "UCWN3xxRkmTPphA17mOOXqPw", "name": "Google Cloud Tech"},
        {"id": "UCcEAq1U4V64R29yMuMzpFfg", "name": "Cloud With Raj"},
    ],
}

# Mots-clés cloud pour filtrer les vidéos pertinentes
CLOUD_KEYWORDS = [
    "tutorial", "explained", "introduction", "overview", "how to",
    "getting started", "fundamentals", "architecture", "best practices",
    "deep dive", "hands on", "demo", "walkthrough", "crash course",
    "compute", "storage", "database", "networking", "security",
    "kubernetes", "docker", "serverless", "machine learning", "ai",
    "openai", "ec2", "s3", "lambda", "vpc", "iam", "rds",
    "virtual machine", "app service", "cosmos", "functions", "azure",
    "bigquery", "cloud run", "gke", "cloud function", "aws", "gcp",
    "devops", "ci/cd", "terraform", "monitoring", "load balancer",
    "container", "microservice", "api gateway", "cdn", "blob",
    "sagemaker", "bedrock", "eks", "ecs", "fargate", "dynamodb",
    "cognitive", "azure ai", "vertex ai", "cloud storage",
    "agent", "agents", "mcp", "foundry", "fabric",
    "sovereignty", "postgresql", "update", "state of the union",
    "learn", "iq", "logic apps", "model router",
]


def load_channels() -> Dict:
    """Charge les chaînes depuis youtube_channels.json ou utilise le défaut."""
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                channels = json.load(f)
            logger.info(f"📂 Chaînes chargées depuis {CHANNELS_FILE}")
            return channels
        except Exception as e:
            logger.warning(f"⚠️  Erreur lecture JSON: {e}")
    logger.info("📂 Utilisation des chaînes par défaut")
    return DEFAULT_CHANNELS


# ─────────────────────────────────────
# 📝 Prompt pour structurer le transcript
# ─────────────────────────────────────
STRUCTURE_PROMPT = """Tu es un expert en documentation technique cloud.

Tu reçois le TRANSCRIPT brut d'une vidéo YouTube éducative sur le cloud computing.

Ton travail : transformer ce transcript verbeux en un fichier Markdown structuré, propre et éducatif.

RÈGLES STRICTES :
1. EXTRAIRE uniquement les informations techniques du transcript
2. SUPPRIMER : "bonjour à tous", "n'oubliez pas de vous abonner", "like", hésitations, répétitions, digressions
3. NE PAS INVENTER d'informations absentes du transcript
4. Écrire en FRANÇAIS
5. Si le transcript est trop pauvre en contenu technique, répondre exactement : SKIP

Format à produire :

# {Titre technique du sujet}

> **Provider** : {Azure | AWS | GCP}
> **Catégorie** : {Compute | Storage | Database | Networking | AI/ML | Security | DevOps | Analytics | Containers | Serverless | Autre}
> **Source** : [{Titre vidéo}]({URL})
> **Chaîne** : {Nom de la chaîne}
> **Durée** : {durée}
> **Date publication** : {date}

## 📄 Résumé

{3-5 phrases résumant ce qui est enseigné}

## 🎯 Points clés

{Liste à puces des concepts importants, 5-10 items}

## 🏗️ Explications détaillées

{Le contenu technique principal, organisé avec des sous-sections ### si nécessaire}

## ⚙️ Étapes pratiques

{Si tutoriel/démo : étapes numérotées. Sinon : "Pas de démonstration pratique dans cette vidéo."}

## 💡 Conseils et bonnes pratiques

{Conseils et warnings mentionnés par le présentateur}

## 🔗 Services et concepts mentionnés

{Liste à puces des services cloud et concepts techniques référencés}
"""


# ─────────────────────────────────────
# 🔧 Fonctions utilitaires
# ─────────────────────────────────────
def extract_video_id(url: str) -> Optional[str]:
    """Extrait l'ID vidéo d'une URL YouTube."""
    patterns = [
        r"(?:v=|\/videos\/|embed\/|youtu\.be\/|\/v\/|watch\?v=)([^#\&\?\s]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def parse_publish_date(video_data: dict) -> Optional[datetime]:
    """Extrait la date de publication depuis les données scrapetube."""
    try:
        time_text = video_data.get("publishedTimeText", {}).get("simpleText", "")
        if not time_text:
            return None

        time_lower = time_text.lower()
        now = datetime.now()

        patterns = [
            (r"(\d+)\s*(minute|min)", "minutes"),
            (r"(\d+)\s*(heure|hour|hr)", "hours"),
            (r"(\d+)\s*(jour|day)", "days"),
            (r"(\d+)\s*(semaine|week)", "weeks"),
            (r"(\d+)\s*(mois|month)", "months"),
            (r"(\d+)\s*(an|année|year)", "years"),
        ]

        for pattern, unit in patterns:
            match = re.search(pattern, time_lower)
            if match:
                value = int(match.group(1))
                deltas = {
                    "minutes": timedelta(minutes=value),
                    "hours": timedelta(hours=value),
                    "days": timedelta(days=value),
                    "weeks": timedelta(weeks=value),
                    "months": timedelta(days=value * 30),
                    "years": timedelta(days=value * 365),
                }
                return now - deltas[unit]

        return None
    except Exception:
        return None


def is_recent_enough(video_data: dict) -> bool:
    """Vérifie si la vidéo est assez récente."""
    pub_date = parse_publish_date(video_data)
    if pub_date is None:
        return True
    return pub_date >= CUTOFF_DATE


def format_duration(seconds: int) -> str:
    """Formate les secondes en durée lisible."""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h{m:02d}min"
    return f"{m}min{s:02d}s"


# ─────────────────────────────────────
# 📺 Extraction YouTube
# ─────────────────────────────────────
def get_transcript(video_id: str) -> Optional[Dict]:
    """Récupère le transcript (sous-titres) d'une vidéo YouTube.
    Compatible avec youtube-transcript-api v1.x
    Supporte les proxies pour contourner le blocage IP cloud.
    """
    try:
        ytt = create_ytt_client()

        # Essayer d'abord en français, puis en anglais
        for langs in [["fr"], ["en"], ["en", "fr"]]:
            try:
                transcript = ytt.fetch(video_id, languages=langs)

                # Construire le texte
                text_parts = []
                duration_sec = 0
                for snippet in transcript:
                    text_parts.append(snippet.text)
                    end = snippet.start + snippet.duration
                    if end > duration_sec:
                        duration_sec = int(end)

                text = " ".join(text_parts)

                if not text.strip():
                    continue

                return {
                    "text": text,
                    "language": langs[0],
                    "is_manual": False,
                    "duration_seconds": duration_sec,
                }
            except Exception:
                continue

        # Dernier essai sans spécifier la langue
        try:
            transcript = ytt.fetch(video_id)

            text_parts = []
            duration_sec = 0
            for snippet in transcript:
                text_parts.append(snippet.text)
                end = snippet.start + snippet.duration
                if end > duration_sec:
                    duration_sec = int(end)

            text = " ".join(text_parts)

            return {
                "text": text,
                "language": "auto",
                "is_manual": False,
                "duration_seconds": duration_sec,
            }
        except Exception as e:
            logger.warning(f"     ⚠️  Transcript indisponible: {e}")
            return None

    except Exception as e:
        logger.warning(f"     ⚠️  Erreur transcript: {e}")
        return None


def get_video_title(video_id: str) -> str:
    """Récupère le vrai titre d'une vidéo via scrapetube search."""
    try:
        for video in scrapetube.get_search(video_id, limit=5):
            if video.get("videoId") == video_id:
                title = video.get("title", {}).get("runs", [{}])[0].get("text", "")
                if title:
                    return title
    except Exception:
        pass
    return f"Video_{video_id}"


def get_channel_videos(channel_id: str, channel_name: str, limit: int = 30) -> List[Dict]:
    """
    Parcourt une chaîne YouTube.
    Filtre : vidéos récentes + pertinentes cloud.
    """
    videos = []
    skipped_old = 0
    skipped_irrelevant = 0

    try:
        for video in scrapetube.get_channel(channel_id, limit=limit * 5, sort_by="newest"):
            title = video.get("title", {}).get("runs", [{}])[0].get("text", "")
            vid = video.get("videoId", "")

            if not title or not vid:
                continue

            # ⏰ FILTRE 1 : Trop ancienne ?
            if not is_recent_enough(video):
                skipped_old += 1
                continue

            # 🔍 FILTRE 2 : Pertinente cloud ?
            title_lower = title.lower()
            if not any(kw in title_lower for kw in CLOUD_KEYWORDS):
                skipped_irrelevant += 1
                continue

            pub_date = parse_publish_date(video)
            pub_date_str = pub_date.strftime("%Y-%m-%d") if pub_date else "unknown"

            videos.append({
                "video_id": vid,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published_date": pub_date_str,
            })

            if len(videos) >= limit:
                break

    except Exception as e:
        logger.error(f"     ❌ Erreur chaîne {channel_name}: {e}")

    if skipped_old > 0:
        logger.info(f"     ⏰ {skipped_old} vidéos trop anciennes (> {MAX_AGE_MONTHS} mois)")
    if skipped_irrelevant > 0:
        logger.info(f"     🔍 {skipped_irrelevant} vidéos pas pertinentes cloud")

    return videos


# ─────────────────────────────────────
# 🤖 Envoyer le transcript au modèle OpenAI
# ─────────────────────────────────────
async def transcript_to_markdown(
    transcript_text: str,
    video_title: str,
    video_url: str,
    channel_name: str,
    duration: str,
    provider: str,
    published_date: str,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Envoie le transcript brut au modèle Azure OpenAI.
    Le modèle retourne un .md structuré.
    """
    # Tronquer si trop long
    max_chars = 60_000
    if len(transcript_text) > max_chars:
        transcript_text = transcript_text[:max_chars] + "\n\n[... TRONQUÉ ...]"

    user_message = (
        f"Titre vidéo : {video_title}\n"
        f"URL : {video_url}\n"
        f"Chaîne : {channel_name}\n"
        f"Provider : {provider}\n"
        f"Durée : {duration}\n"
        f"Date publication : {published_date}\n\n"
        f"--- TRANSCRIPT ---\n\n{transcript_text}"
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": STRUCTURE_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=4096,
            )

            result = response.choices[0].message.content

            if result and result.strip().startswith("SKIP"):
                logger.info("     ⏭️  LLM a dit SKIP (contenu insuffisant)")
                return None

            return result

        except Exception as e:
            logger.warning(f"     ⚠️  Tentative {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                wait = attempt * 5
                logger.info(f"     ⏳ Retry dans {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"     ❌ Échec après {max_retries} tentatives")
                return None


# ─────────────────────────────────────
# 🚀 Traiter UNE vidéo
# ─────────────────────────────────────
async def process_one_video(
    video_id: str,
    title: str,
    url: str,
    channel_name: str,
    provider: str,
    published_date: str = "unknown",
) -> bool:
    """
    Pipeline complet pour une vidéo :
    1. Extraire le transcript
    2. Sauvegarder le brut dans data/raw/{provider}/
    3. Envoyer au modèle OpenAI
    4. Sauvegarder le .md dans data/processed/{provider}/
    """
    logger.info(f"\n  🎬 {title[:80]}")
    logger.info(f"     📅 {published_date} | 📺 {channel_name}")

    # ── Chemin de sortie : data/processed/{provider}/ ──
    output_dir = os.path.join(PROCESSED_DIR, provider.lower())
    os.makedirs(output_dir, exist_ok=True)

    safe_name = re.sub(r'[^\w\s-]', '', title)[:60].strip().replace(' ', '_').lower()
    md_filename = f"yt_{safe_name}.md"
    md_path = os.path.join(output_dir, md_filename)

    # Déjà traité ?
    if os.path.exists(md_path):
        logger.info(f"     ⏭️  Déjà traité → {provider}/{md_filename}")
        return False

    # ── ÉTAPE 1 : Extraire le transcript ──
    logger.info(f"     📝 Extraction du transcript...")
    transcript = get_transcript(video_id)
    if not transcript:
        logger.warning(f"     ❌ Pas de transcript disponible")
        return False

    duration = format_duration(transcript["duration_seconds"])
    quality = "manuel" if transcript["is_manual"] else "auto-généré"
    logger.info(f"     📝 Transcript OK : {transcript['language']} ({quality}), {duration}")

    # Filtrer par durée
    if transcript["duration_seconds"] < 120:
        logger.info(f"     ⏭️  Trop courte (< 2min)")
        return False
    if transcript["duration_seconds"] > 10800:
        logger.info(f"     ⏭️  Trop longue (> 3h)")
        return False

    # ── ÉTAPE 2 : Sauvegarder le transcript brut ──
    raw_provider_dir = os.path.join(RAW_DIR, provider.lower())
    os.makedirs(raw_provider_dir, exist_ok=True)
    raw_path = os.path.join(raw_provider_dir, f"{video_id}.json")

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({
            "video_id": video_id,
            "title": title,
            "url": url,
            "channel": channel_name,
            "provider": provider,
            "published_date": published_date,
            "transcript": transcript,
            "extracted_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"     💾 Brut sauvé → raw/{provider}/{video_id}.json")

    # ── ÉTAPE 3 : Envoyer au modèle OpenAI ──
    logger.info(f"     🤖 Envoi au modèle Azure OpenAI...")
    markdown = await transcript_to_markdown(
        transcript_text=transcript["text"],
        video_title=title,
        video_url=url,
        channel_name=channel_name,
        duration=duration,
        provider=provider,
        published_date=published_date,
    )

    if not markdown:
        return False

    # ── ÉTAPE 4 : Sauvegarder le .md ──
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"     ✅ → processed/{provider}/{md_filename} ({len(markdown):,} chars)")
    return True


# ─────────────────────────────────────
# 🚀 Traiter un PROVIDER (azure, aws, gcp)
# ─────────────────────────────────────
async def process_provider(
    provider: str,
    channels: List[Dict],
    max_videos: int = 20,
    concurrent: int = 2,
) -> int:
    """
    Pour un provider (ex: azure) :
    1. Parcourt chaque chaîne YouTube
    2. Liste les vidéos récentes et pertinentes
    3. Traite chaque vidéo (transcript → LLM → .md)
    4. Sauvegarde dans data/processed/{provider}/
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"☁️  {provider.upper()}")
    logger.info(f"📁 Sortie : data/processed/{provider}/")
    logger.info(f"⏰ Filtre : vidéos des {MAX_AGE_MONTHS} derniers mois")
    logger.info(f"{'='*60}")

    all_videos = []

    # ── Parcourir chaque chaîne YouTube ──
    for ch in channels:
        logger.info(f"\n  📺 Chaîne : {ch['name']}")
        logger.info(f"     🔗 https://www.youtube.com/channel/{ch['id']}")

        videos = get_channel_videos(ch["id"], ch["name"], limit=max_videos)
        logger.info(f"     ✅ {len(videos)} vidéos récentes et pertinentes")

        for v in videos:
            v["channel_name"] = ch["name"]
            v["provider"] = provider
        all_videos.extend(videos)

    # Dédupliquer
    seen = set()
    unique = []
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique.append(v)

    logger.info(f"\n🎬 {len(unique)} vidéos uniques à traiter pour {provider.upper()}")

    if not unique:
        return 0

    # ── Traiter avec concurrence limitée ──
    semaphore = asyncio.Semaphore(concurrent)

    async def _process(v):
        async with semaphore:
            return await process_one_video(
                video_id=v["video_id"],
                title=v["title"],
                url=v["url"],
                channel_name=v["channel_name"],
                provider=v["provider"],
                published_date=v.get("published_date", "unknown"),
            )

    results = await asyncio.gather(*[_process(v) for v in unique])
    success = sum(1 for r in results if r)

    logger.info(f"\n✅ {provider.upper()}: {success}/{len(unique)} vidéos → data/processed/{provider}/")
    return success


# ─────────────────────────────────────
# 🔗 Traiter une seule URL
# ─────────────────────────────────────
async def process_single_url(url: str, provider: str = "azure", channel: str = "Unknown"):
    """Traite une seule URL YouTube."""
    video_id = extract_video_id(url)
    if not video_id:
        logger.error(f"❌ URL invalide : {url}")
        return False

    # Récupérer le vrai titre
    title = get_video_title(video_id)
    logger.info(f"📌 Titre : {title}")

    return await process_one_video(
        video_id=video_id,
        title=title,
        url=url,
        channel_name=channel,
        provider=provider,
    )


# ─────────────────────────────────────
# 🏁 Main
# ─────────────────────────────────────
async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="🎬 YouTube → .md structuré par provider",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Tester avec une seule vidéo AWS
  python youtube_extractor.py --url "https://youtube.com/watch?v=XXX" --provider aws

  # Extraire les vidéos Azure des 12 derniers mois
  python youtube_extractor.py --provider azure --max-videos 10 --max-age 12

  # Extraire TOUT (Azure + AWS + GCP)
  python youtube_extractor.py --provider all --max-videos 5

  # Mode prudent
  python youtube_extractor.py --provider aws --concurrent 1 --max-age 6

Résultat :
  data/processed/azure/yt_xxx.md
  data/processed/aws/yt_xxx.md
  data/processed/gcp/yt_xxx.md
        """,
    )
    parser.add_argument("--url", type=str, help="Une seule URL YouTube")
    parser.add_argument("--provider", type=str,
                        choices=["azure", "aws", "gcp", "all"], default="all")
    parser.add_argument("--max-videos", type=int, default=20,
                        help="Max vidéos par chaîne (défaut: 20)")
    parser.add_argument("--concurrent", type=int, default=2,
                        help="Appels LLM simultanés (défaut: 2)")
    parser.add_argument("--max-age", type=int, default=24,
                        help="Âge max en mois (défaut: 24)")
    parser.add_argument("--channel", type=str, default="Unknown",
                        help="Nom chaîne (pour --url)")
    args = parser.parse_args()

    # Mettre à jour le filtre de date
    global MAX_AGE_MONTHS, CUTOFF_DATE
    MAX_AGE_MONTHS = args.max_age
    CUTOFF_DATE = datetime.now() - timedelta(days=MAX_AGE_MONTHS * 30)

    # Charger les chaînes
    all_channels = load_channels()

    # Affichage initial
    logger.info("=" * 60)
    logger.info("🎬 YOUTUBE TRANSCRIPT → MARKDOWN STRUCTURÉ")
    logger.info("=" * 60)
    logger.info(f"📂 Script      : {SCRIPT_DIR}")
    logger.info(f"📂 Data        : {DATA_DIR}")
    logger.info(f"📂 Raw         : {RAW_DIR}")
    logger.info(f"📂 Processed   : {PROCESSED_DIR}")
    logger.info(f"📂 .env        : {env_path} (existe: {os.path.exists(env_path)})")
    logger.info(f"🔑 Endpoint    : {AZURE_OPENAI_ENDPOINT}")
    logger.info(f"🔑 Deployment  : {AZURE_OPENAI_DEPLOYMENT}")
    logger.info(f"🌐 Proxy       : {'✅ ' + PROXY_URL.split('@')[-1] if PROXY_URL else '❌ Pas de proxy (risque de blocage sur IP cloud)'}")
    logger.info(f"⏰ Max âge     : {MAX_AGE_MONTHS} mois")
    logger.info("")

    # Vérifier la config
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        logger.error("❌ AZURE_OPENAI_ENDPOINT ou AZURE_OPENAI_API_KEY manquant dans .env")
        return

    if not AZURE_OPENAI_DEPLOYMENT:
        logger.error("❌ AZURE_OPENAI_DEPLOYMENT_NAME manquant dans .env")
        return

    if not PROXY_URL:
        logger.warning("⚠️  Pas de PROXY_URL configuré dans .env")
        logger.warning("⚠️  YouTube bloque les IPs cloud (Azure, AWS, GCP)")
        logger.warning("⚠️  Ajoutez PROXY_URL=http://user:pass@proxy:port dans votre .env")
        logger.warning("⚠️  Ou exécutez ce script depuis un PC local (IP résidentielle)")
        logger.warning("")

    try:
        if args.url:
            # ── Mode : une seule vidéo ──
            await process_single_url(args.url, args.provider, args.channel)
        else:
            # ── Mode : parcourir les chaînes ──
            providers = list(all_channels.keys()) if args.provider == "all" else [args.provider]

            total = 0
            for p in providers:
                channels = all_channels.get(p, [])
                if not channels:
                    logger.warning(f"⚠️  Aucune chaîne configurée pour {p}")
                    continue
                count = await process_provider(p, channels, args.max_videos, args.concurrent)
                total += count

            # ── Rapport final ──
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 RAPPORT FINAL")
            logger.info(f"{'='*60}")
            logger.info(f"⏰ Période : {MAX_AGE_MONTHS} derniers mois")
            logger.info(f"✅ Nouveaux .md : {total}")

            for p in providers:
                p_dir = os.path.join(PROCESSED_DIR, p.lower())
                if os.path.exists(p_dir):
                    files = [f for f in os.listdir(p_dir) if f.endswith(".md")]
                    logger.info(f"   📂 processed/{p}/ : {len(files)} fichiers .md")

            logger.info(f"📝 Log : {log_file}")
            logger.info(f"{'='*60}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())