"""
test_api.py - Console Interactive de test du Streaming Backend Subul
"""
import asyncio
import httpx
import json

API_URL = "http://localhost:8000/api/chat"

async def tester_streaming_api():
    print("🚀 Démarrage de la console Subul (Mode Streaming Interactif)...")
    print("💡 Tapez 'quitter' ou 'exit' pour fermer le test.\n")
    print("═" * 60)
    
    # On garde le même ID pour que l'IA se souvienne de la conversation
    session_id = "test-terminal-interactif-123"

    # On garde le client ouvert pour enchaîner les questions
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            # 1. On attend TA question dans le terminal
            user_msg = input("\n🗣️ Vous : ")
            
            # Condition de sortie
            if user_msg.lower().strip() in ["quitter", "quit", "exit"]:
                print("👋 Fermeture de la console de test.")
                break
            
            if not user_msg.strip():
                continue

            # 2. On prépare la requête
            payload = {
                "session_id": session_id,
                "message": user_msg,
                "profile": {
                    "name": "Testeur Terminal",
                    "level": "débutant",
                    "background": "AWS"
                }
            }

            print("🤖 Agent : ", end="", flush=True)

            try:
                # 3. On envoie et on écoute le flux en temps réel
                async with client.stream("POST", API_URL, json=payload) as response:
                    
                    if response.status_code != 200:
                        print(f"\n❌ Erreur API : Code {response.status_code}")
                        continue

                    # Lecture mot par mot
                    async for chunk in response.aiter_lines():
                        if chunk.strip():
                            try:
                                data = json.loads(chunk)
                                mot = data.get("chunk", "")
                                print(mot, end="", flush=True)
                            except json.JSONDecodeError:
                                pass # On ignore les lignes mal formées
                
                print() # Retour à la ligne quand l'IA a fini de parler

            except Exception as e:
                print(f"\n❌ Erreur de connexion au serveur : {e}")
                print("💡 Vérifiez que 'python api.py' tourne bien sur le port 8000.")
                break

if __name__ == "__main__":
    # Pour Windows, évite certaines erreurs liées à asyncio
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(tester_streaming_api())