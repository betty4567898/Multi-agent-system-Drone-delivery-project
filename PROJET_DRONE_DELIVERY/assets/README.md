# 📂 Assets — Logo UEMF + Captures d'écran

## 🎓 Logo UEMF (obligatoire)

**Sauvegarde le logo UEMF que tu as déjà ici** sous le nom :

```
assets/uemf_logo.png
```

Tu peux télécharger le logo officiel depuis : https://www.ueuromed.org/
ou utiliser celui que tu m'as envoyé dans le chat.

---

## 📸 Captures d'écran à ajouter (optionnel mais recommandé)

Place ces 6 captures dans `assets/screenshots/` :

| Nom du fichier | Description | Section dans le rapport |
|----------------|-------------|------------------------|
| `dashboard_full.png` | Vue complète du dashboard (carte + stats + flotte) | 8.3 |
| `map_fleet.png` | Zoom sur les 5 drones autour de l'UEMF | 8.3 |
| `order_form.png` | Formulaire "Passer une commande" rempli | 8.3 |
| `contract_net_events.png` | Log des événements Contract-Net (CFP → PROPOSE → ACCEPT) | 5.2 |
| `result_stats.png` | Stats après plusieurs livraisons | 9.4 |
| `result_events.png` | Détail des événements FIPA-ACL | 9.4 |

### Comment faire des captures de qualité ?

1. Lance le projet : `python main.py`
2. Passe quelques commandes
3. Attends que les drones livrent
4. Sur Windows : **Win + Shift + S** → sélectionne la zone → enregistre en PNG
5. Renomme et place dans `assets/screenshots/`

---

## ▶️ Générer le PDF

Une fois les images ajoutées :

```powershell
# Installer Playwright (1 seule fois)
pip install playwright
playwright install chromium

# Générer le PDF
python tools/generate_rapport.py
```

→ Le fichier `RAPPORT.pdf` apparaît à la racine du projet.

### Alternative sans installation

Si tu ne veux pas installer Playwright :

1. Lance : `python tools/generate_rapport.py`
   (cela génère `tools/rapport_final.html` avec les images intégrées)
2. Ouvre ce fichier HTML dans **Chrome** ou **Edge**
3. **CTRL + P** → "Destination : Enregistrer en PDF"
4. Cochez "Graphiques d'arrière-plan" pour conserver les styles
5. Cliquez sur "Enregistrer" → tu obtiens un PDF identique au rendu navigateur

---

## ❓ Si certaines images manquent

Pas de souci ! Le générateur les remplace par des **placeholders élégants** avec le nom du fichier manquant.
Tu peux relancer le script après avoir ajouté les images.
