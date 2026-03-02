"""
architecte_agent.py — Agent ARCHITECTE (Production Ready)

Évolutions Cloud / Production :
  - 100% Asynchrone (AsyncAzureOpenAI, asyncio.to_thread).
  - Multi-Tenant (utilisation du session_id).
  - Découplage (Injection de la Mémoire globale).
  - Génération Mermaid (F5) non-bloquante.
"""

import os
import sys
import re
import math
import asyncio
from dotenv import load_dotenv
from ddgs import DDGS

# ⚡ Imports Asynchrones
from openai import AsyncAzureOpenAI

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BASE_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)   # permet 'from memory_management import ...'

# ── Configuration ─────────────────────────────────────────────────────────────
load_dotenv(os.path.join(_ROOT_DIR, "00_Config", ".env.txt"))

# ⚡ Client OpenAI Asynchrone
oai_client = AsyncAzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
CHAT_MODEL = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_ARCHITECT = """Tu es l'Architecte DoxariaEyeQ, expert impartial en cloud computing.
Missions :
1. COMPARAISONS : Présente des tableaux Markdown objectifs (Avantages / Inconvénients / Prix / Use-case).
2. DIAGRAMMES   : Si du code Terraform/YAML/CloudFormation est fourni, génère un diagramme Mermaid.js.
3. COÛTS        : Calcule et explique les coûts mensuels estimés avec des hypothèses claires.
4. CARRIÈRE     : Donne des conseils sur les certifications et compétences les plus demandées.
5. BENCHMARKS   : Cite des données réelles issues du Web (sources incluses).

BAN absolu : Ne favorise aucun cloud. Sois toujours neutre et factuel.
Format : Markdown enrichi (tableaux, listes, Mermaid blocks).
"""


# ── DuckDuckGo Search (Asynchrone via Threading) ─────────────────────────────
async def live_web_search(query: str, top: int = 4) -> str:
    """Recherche web déléguée à un thread séparé pour données volatiles."""
    print(f"   🌐 Recherche Web Architecte : {query}")
    try:
        
        # ⚡ Prévention du blocage I/O
        results = await asyncio.to_thread(DDGS().text, query, max_results=top)
        
        if not results:
            return "Aucun résultat trouvé sur le web."
        snippets = [
            f"**[{r.get('title', 'Titre')}]({r.get('href', '')})**\n{r.get('body', '')}"
            for r in results
        ]
        return "\n\n".join(snippets)
    except Exception as e:
        print(f"⚠️ Erreur DuckDuckGo: {e}")
        return f"⚠️ Impossible d'accéder aux données en direct."


# ── Calculator Tool (Synchrone car purement mathématique) ─────────────────────
def calculate_cloud_cost(
    service      : str,
    units        : float,
    unit_price   : float,
    hours_per_day: float = 24,
    days_per_month: int  = 30,
) -> dict:
    """Estimation mathématique de coût mensuel."""
    monthly = units * unit_price * hours_per_day * days_per_month
    return {
        "service"       : service,
        "units"         : units,
        "unit_price_usd": unit_price,
        "monthly_usd"   : round(monthly, 2),
        "annual_usd"    : round(monthly * 12, 2),
    }


# ── Code-to-Diagram Asynchrone (F5) ───────────────────────────────────────────
async def generate_mermaid_diagram(infra_code: str) -> str:
    """Génère un diagramme de façon asynchrone pour ne pas geler le serveur."""
    prompt = f"""Analyse ce code d'infrastructure cloud et génère un diagramme Mermaid.js.
Identifie les ressources (VPC, Subnets, EC2, SG, RDS, Load Balancer, etc.) et leurs relations.
Retourne UNIQUEMENT le bloc Mermaid, sans texte autour.

Code à analyser :

Format de sortie attendu :
```mermaid
graph TD
    ...
```"""
    try:
        # ⚡ Appel réseau non-bloquant
        resp = await oai_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "Tu es un expert en architecture cloud et Mermaid.js."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=800,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ [Mermaid] Erreur de génération : {e}")
        return "⚠️ Erreur lors de la génération du diagramme Mermaid."


# ── Détection de code infra (Synchrone : Regex rapide) ────────────────────────
def detect_infra_code(text: str) -> str | None:
    """Retourne le bloc de code extrait si du Terraform/YAML/CF est détecté."""
    code_block = re.search(r"```(?:terraform|yaml|yml|json|hcl|cloudformation)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if code_block:
        return code_block.group(1).strip()
    
    keywords = ["resource \"aws_", "azurerm_", "google_", "AWSTemplateFormatVersion",
                 "apiVersion:", "kind: Deployment", "module \""]
    if any(k in text for k in keywords):
        return text
    return None


# ══════════════════════════════════════════════════════════════════════════════
class ArchitecteAgent:
    """Agent Architecte Asynchrone : comparaisons, benchmarks, diagrammes."""

    # 💉 1. Injection de la mémoire depuis l'Orchestrateur
    def __init__(self, memory):
        self.memory = memory
        print("🏛️ Architecte Asynchrone initialisé — Stratège impartial multi-cloud")

    # ⚡ 2. Support du Multi-Tenant et Asynchronisme
    async def repondre(self, session_id: str, user_message: str, fetch_live: bool = True) -> str:
        """Pipeline de l'Architecte."""
        extra_context = ""

        # ② Détection de bloc de code infra (F5)
        infra_code = detect_infra_code(user_message)
        if infra_code:
            print(f"   📐 Code infra détecté pour la session {session_id} → génération Mermaid…")
            # ⚡ Await obligatoire ici !
            diagram = await generate_mermaid_diagram(infra_code)
            
            # Sauvegarde en mémoire de l'action accomplie
            self.memory.add_user_message(session_id, user_message)
            self.memory.add_agent_message(session_id, f"Diagramme généré.\n{diagram}")
            return f"Voici le diagramme d'architecture généré :\n\n{diagram}"

        # ③ Live Search DuckDuckGo (Asynchrone)
        if fetch_live:
            live_query = f"cloud comparison pricing benchmark {user_message}"
            # ⚡ Await obligatoire !
            live_data  = await live_web_search(live_query, top=3)
            extra_context = f"\n\n📊 DONNÉES WEB EN TEMPS RÉEL (DuckDuckGo) :\n{live_data}"

        # ④ Préparation du contexte (Multi-Tenant)
        messages = [{"role": "system", "content": SYSTEM_ARCHITECT}]

        # ⚡ Récupération Asynchrone de la mémoire longue
        ctx_long = await self.memory.get_memory_context_for_prompt(session_id)
        if ctx_long:
            messages.append({"role": "system", "content": ctx_long})

        if extra_context:
            messages.append({"role": "system", "content": extra_context})

        # Ajout de l'historique court ciblé sur la session
        messages.extend(self.memory.get_short_history(session_id))
        messages.append({"role": "user", "content": user_message})

        # ⚡ Appel LLM Asynchrone
        try:
            resp = await oai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                max_tokens=1800,
                temperature=0.2,
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ [Architecte LLM] Erreur : {e}")
            answer = "Je rencontre une difficulté pour analyser cette architecture. Pouvons-nous réessayer ?"

        # Sauvegarde isolée par utilisateur
        self.memory.add_user_message(session_id, user_message)
        self.memory.add_agent_message(session_id, answer)
        return answer

    # ── Outil Calculator ──────────────────────────────────────────────────────
    def estimate_cost(self, service: str, units: float, unit_price: float, hours: float = 24, days: int = 30) -> str:
        result = calculate_cloud_cost(service, units, unit_price, hours, days)
        lines = [
            f"💰 **Estimation de coût — {result['service']}**",
            f"- Unités          : {result['units']}",
            f"- Prix unitaire   : ${result['unit_price_usd']}/h",
            f"- Coût mensuel    : **${result['monthly_usd']}**",
            f"- Coût annuel     : **${result['annual_usd']}**",
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TEST STANDALONE
# ══════════════════════════════════════════════════════════════════════════════
async def _test():
    # ⚠️ Pour tester en local, on crée une mémoire factice
    from memory_management import MemoryManager, LocalJSONAdapter
    test_memory = MemoryManager(oai_client=oai_client, chat_model=CHAT_MODEL, db_adapter=LocalJSONAdapter())
    
    ag = ArchitecteAgent(memory=test_memory)
    session_test = "archi-test-888"

    print("\n💡 Test Comparaison :")
    resp_comp = await ag.repondre(session_test, "Compare AWS S3 et Azure Blob Storage en termes de coûts")
    print(resp_comp)

    print("\n---\n📐 Test Code to Diagram :")
    tf_code = '''
resource "aws_vpc" "main" { cidr_block = "10.0.0.0/16" }
resource "aws_subnet" "public" { vpc_id = aws_vpc.main.id; cidr_block = "10.0.1.0/24" }
resource "aws_instance" "web" { ami = "ami-123"; instance_type = "t3.micro"; subnet_id = aws_subnet.public.id }
    '''
    resp_diag = await ag.repondre(session_test, tf_code)
    print(resp_diag)

    print("\n---\n💰 Cost estimate:")
    print(ag.estimate_cost("EC2 t3.micro", 1, 0.0104))

if __name__ == "__main__":
    asyncio.run(_test())