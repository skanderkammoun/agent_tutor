"""
Aplatit tous les fichiers de azure-docs/ et ses sous-dossiers
vers data/raw/azure/ en renommant les doublons.
"""
import os
import shutil

BASE = os.path.expanduser("~/cloudfiles/code/Users/Skander.Kammoun/Agent_Tuteur_Subul/01_Knowledge_Base/data/raw/azure")
SOURCE = os.path.join(BASE, "azure-docs")
DEST = BASE

if not os.path.exists(SOURCE):
    print(f"❌ Dossier introuvable : {SOURCE}")
    exit(1)

moved = 0
skipped = 0
renamed = 0

for root, dirs, files in os.walk(SOURCE):
    for filename in files:
        src_path = os.path.join(root, filename)
        dest_path = os.path.join(DEST, filename)

        # Si le fichier existe déjà, ajouter un préfixe unique
        if os.path.exists(dest_path):
            # Utiliser le nom du sous-dossier comme préfixe
            subfolder = os.path.basename(root)
            new_name = f"{subfolder}_{filename}"
            dest_path = os.path.join(DEST, new_name)
            
            # Si toujours en doublon, ajouter un compteur
            counter = 1
            while os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                new_name = f"{subfolder}_{name}_{counter}{ext}"
                dest_path = os.path.join(DEST, new_name)
                counter += 1
            renamed += 1

        try:
            shutil.move(src_path, dest_path)
            moved += 1
        except Exception as e:
            print(f"⚠️  Erreur: {src_path} → {e}")
            skipped += 1

print(f"\n✅ {moved} fichiers déplacés")
print(f"🔄 {renamed} fichiers renommés (doublons)")
print(f"⚠️  {skipped} fichiers ignorés (erreurs)")

# Supprimer le dossier azure-docs vide
try:
    shutil.rmtree(SOURCE)
    print(f"🗑️  Dossier azure-docs supprimé")
except Exception as e:
    print(f"⚠️  Impossible de supprimer azure-docs: {e}")

# Compter le résultat
total = len([f for f in os.listdir(DEST) if os.path.isfile(os.path.join(DEST, f))])
print(f"\n📂 {DEST}/ contient maintenant {total} fichiers")