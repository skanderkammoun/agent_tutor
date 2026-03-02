import os
import shutil

# Chemins des dossiers
BASE_DIR = os.path.expanduser("~/cloudfiles/code/Users/Skander.Kammoun/Agent_Tuteur_Subul/01_Knowledge_Base/data")
RAW_DIR = os.path.join(BASE_DIR, "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

def move_md_files(provider):
    raw_path = os.path.join(RAW_DIR, provider)
    processed_path = os.path.join(PROCESSED_DIR, provider)
    os.makedirs(processed_path, exist_ok=True)  # Crée le dossier processed si inexistant

    # Parcourir tous les fichiers dans le dossier raw/provider
    for root, _, files in os.walk(raw_path):
        for file in files:
            if file.endswith(".md"):  # Vérifier l'extension .md
                src_path = os.path.join(root, file)
                dest_path = os.path.join(processed_path, file)

                # Déplacer le fichier
                try:
                    shutil.move(src_path, dest_path)
                    print(f"✅ Déplacé : {src_path} → {dest_path}")
                except Exception as e:
                    print(f"❌ Erreur lors du déplacement de {src_path} : {e}")

def main():
    # Déplacer les fichiers pour chaque provider
    for provider in ["aws", "gcp", "azure"]:
        print(f"📂 Déplacement des fichiers .md pour {provider}...")
        move_md_files(provider)
    print("✅ Tous les fichiers .md ont été déplacés.")

if __name__ == "__main__":
    main()