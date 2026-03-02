"""
test_rag_llmops.py — DoxariaEyeQ : Pipeline d'Évaluation QA & RAG (LLMOps)

🎯 NOUVEAUTÉS TECH LEAD :
- Compatible avec la nouvelle architecture BrainAgent / MemoryAgentProxy.
- Évaluation directe de l'agent qui partira en production.
"""

import os
import sys
import time
import json
import asyncio
from dotenv import load_dotenv

# ── 🛠️ 1. GESTION DES CHEMINS ──────────────────────────────
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))      
_ROOT_DIR = os.path.dirname(_TEST_DIR)                      
_AGENTS_DIR = os.path.join(_ROOT_DIR, "03_Agents")          

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
if _AGENTS_DIR not in sys.path:
    sys.path.insert(0, _AGENTS_DIR)

# Chargement sécurisé de l'environnement pour le Juge OpenAI
env_path = os.path.join(_ROOT_DIR, "00_Config", ".env.txt")
load_dotenv(dotenv_path=env_path)

# IMPORT DU NOUVEAU CERVEAU
from agent_rag import BrainAgent
from openai import AsyncAzureOpenAI

# ── 📊 2. CHARGEMENT DU "GOLDEN DATASET" ────────────────────────────────────
dataset_path = os.path.join(_TEST_DIR, "golden_dataset.json")

try:
    with open(dataset_path, "r", encoding="utf-8") as f:
        GOLDEN_DATASET = json.load(f)
    print(f"📦 Golden Dataset chargé avec succès : {len(GOLDEN_DATASET)} questions.")
except FileNotFoundError:
    print(f"❌ Erreur : Le fichier dataset est introuvable au chemin : {dataset_path}")
    sys.exit(1)

# ── ⚖️ 3. LE PROMPT DU JUGE ────────────────
SYSTEM_JUDGE = """Tu es un Juge QA LLMOps impitoyable et expert en Cloud Computing (AWS/Azure). 
Ta mission est d'évaluer la qualité d'une réponse générée par rapport à une question.
Tu dois répondre STRICTEMENT au format JSON."""

def get_eval_prompt(question: str, generated_answer: str) -> str:
    return f"""
Évalue la réponse générée par l'Agent.

QUESTION DE L'APPRENANT : 
"{question}"

RÉPONSE GÉNÉRÉE PAR L'AGENT : 
"{generated_answer}"

Calcule deux métriques (score de 0.0 à 1.0). SOIS SÉVÈRE :
1. "helpfulness" : La réponse aide-t-elle concrètement l'étudiant ? (1.0 = Réponse complète et pédagogique, 0.0 = Ne répond pas à la question).
2. "faithfulness" : L'agent semble-t-il sûr de ses faits techniques sans inventer ? (1.0 = Explications techniques précises, 0.0 = Hallucination évidente ou réponse vague).

Format JSON attendu :
{{
    "helpfulness": <float>,
    "faithfulness": <float>,
    "reason": "<Explication très courte de 15 mots maximum>"
}}
"""

# ── 🚀 4. LE MOTEUR D'ÉVALUATION ────────────────────────────────
async def run_qa_pipeline():
    print("\n" + "═"*65)
    print("  🧪 Démarrage de la suite de tests QA (BrainAgent)")
    print("═"*65 + "\n")

    # 1. Initialisation de ton Agent de Production
    brain = BrainAgent()
    await brain.setup()
    
    # 2. On récupère le proxy de mémoire (Mode texte, Français par défaut)
    agent_tuteur = brain.get_agent(lang="fr", is_audio=False)

    # 3. Client OpenAI pour le Juge
    judge_client = AsyncAzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-15-preview"
    )
    JUDGE_MODEL = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    
    results = []
    
    # On simule un étudiant de test
    eval_user_id = "etudiant_qa_tester"

    for idx, item in enumerate(GOLDEN_DATASET, 1):
        print(f"▶️ [{idx}/{len(GOLDEN_DATASET)}] Test : {item['id']} ({item.get('cloud_target', 'Général')})")
        
        # Une session différente par question pour ne pas polluer le contexte
        test_session_id = f"eval-session-{item['id']}"
        start_time = time.time()
        
        # --- ÉTAPE A : Génération de la Réponse via ton Pipeline RAG réel ---
        try:
            # On force le français comme dans l'API
            message_securise = item['question'] + "\n\n(Règle stricte: Formule ta réponse IMPÉRATIVEMENT en Français.)"
            response = await agent_tuteur.run(
                message=message_securise, 
                user_id=eval_user_id, 
                session_id=test_session_id
            )
            answer = response.text
        except Exception as e:
            print(f"   ❌ Erreur de génération : {e}")
            answer = "Erreur de l'agent."
            
        latency = time.time() - start_time
        
        # --- ÉTAPE B : Jugement ---
        eval_prompt = get_eval_prompt(item['question'], answer)
        
        try:
            judge_resp = await judge_client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": eval_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                timeout=20.0
            )
            scores = json.loads(judge_resp.choices[0].message.content.strip())
        except Exception as e:
            print(f"   ⚠️ [Erreur du Juge] : {e}")
            scores = {"helpfulness": 0.0, "faithfulness": 0.0, "reason": "Échec de l'évaluation."}

        record = {
            "id": item["id"],
            "latency_sec": round(latency, 2),
            "helpfulness": float(scores.get("helpfulness", 0.0)),
            "faithfulness": float(scores.get("faithfulness", 0.0)),
            "judge_reason": scores.get("reason", "N/A")
        }
        results.append(record)
        
        print(f"   ⏱️ Latency           : {record['latency_sec']}s")
        print(f"   🎯 Helpfulness       : {record['helpfulness']}")
        print(f"   🛡️ Faithfulness      : {record['faithfulness']}")
        print(f"   💡 Juge (Raison)     : {record['judge_reason']}\n")

        await asyncio.sleep(1)

    # ── 📈 5. BILAN FINAL ────────────────────────────────────────────────
    avg_latency = sum(r['latency_sec'] for r in results) / len(results) if results else 0
    avg_helpfulness = sum(r['helpfulness'] for r in results) / len(results) if results else 0
    avg_faithfulness = sum(r['faithfulness'] for r in results) / len(results) if results else 0

    print("════════════════════════════════════════════════")
    print("📊 RAPPORT FINAL DE NON-RÉGRESSION")
    print("════════════════════════════════════════════════")
    print(f"Total des tests exécutés    : {len(results)}")
    print(f"Latence moyenne             : {round(avg_latency, 2)}s")
    print(f"Helpfulness moyenne         : {round(avg_helpfulness * 100, 1)}%")
    print(f"Faithfulness moyenne        : {round(avg_faithfulness * 100, 1)}%")
    print("════════════════════════════════════════════════")

    report_path = os.path.join(_TEST_DIR, "qa_report_brainagent.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print(f"📄 Rapport détaillé sauvegardé dans : {report_path}")

if __name__ == "__main__":
    asyncio.run(run_qa_pipeline())