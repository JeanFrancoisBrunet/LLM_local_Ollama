# LLM Raspberry Pi 5 — Interface locale multi-modèles

Interface graphique Tkinter pour dialoguer avec plusieurs **LLM exécutés localement via Ollama**, directement sur un Raspberry Pi 5 (16 Go RAM, SSD NVMe), sans dépendance à un service cloud.

## Modèles intégrés
| Onglet         | Modèle(s)                                            | Caractéristiques                                                                          |
|---             |---                                                   |---                                                                                        |
| 🦙 Llama       | `llama32-8k:latest` / `llama3.2:3b` (menu déroulant) | Contexte 8K (compact, rapide) / Contexte 128K (polyvalent, très rapide) — 2,0 Go          |
| 🌬 Mistral     | `mistral:7b`                                         | Généraliste, bon équilibre vitesse/qualité — contexte 32K, 4,4 Go                         |
| Qwen 2.5 – 7B  | `qwen2.5:7b`                                         | Généraliste multilingue, raisonnement (Alibaba) — contexte 128K, 4,7 Go                   |
| DeepSeek-Coder | `deepseek-coder:6.7b`                                | Spécialisé Python / C / JS — contexte 16K, 3,8 Go                                         |
| Gemma 2 – 9B   | `gemma2:9b`                                          | Rédaction naturelle, style fluide (Google) — contexte 8K, 5,4 Go                          |
| 🦙 Vision 11B  | `llama3.2-vision:11b`                                | Multimodal txt + images — contexte 128K, 7,8 Go, avec **Moondream** intégré (vision ultra-rapide, 1,7 Go, questions en anglais uniquement) |

Chaque onglet est un chat indépendant avec son propre historique.

## Fonctionnalités

### Chat et streaming
- Réponses en **streaming** (affichage au fil de la génération), avec bouton **⏹ STOP** pour interrompre une génération en cours.
- Historique conservé par modèle, archivé en JSON dans `historiques/` (fenêtre glissante de 10 paires user/assistant en mémoire active, jusqu'à 20 sessions archivées par fichier).
- Bouton dédié pour effacer l'historique d'un onglet.

### Pièces jointes
- Ajout de fichiers (documents, images) joints au message.
- Extraction de texte PDF via **pdfminer.six**.
- Images (`.jpg`, `.jpeg`, `.png`, max 20 Mo) encodées en base64 et envoyées aux modèles compatibles vision.

### Questions rapides
- Bibliothèque de questions prédéfinies classées par thème (Analyse de documents, Analyse d'images, Code & programmation, Résolution de problèmes, Autres), insérables en un clic dans la zone de saisie.

### Onglet Vision — Llama 3.2 Vision & Moondream
- Mode **Llama 3.2 Vision 11B** : analyse d'image en français, image jointe au message courant uniquement (non conservée dans l'historique, limitation du modèle).
- Mode **Moondream** (activable/désactivable) : vision légère et rapide, questions en anglais uniquement, avec une bibliothèque de questions prêtes à l'emploi (Describe, Who/What?, Time period?, Extract text, One sentence, Style/Colors, Layout, Custom…).

### Lecture vocale (TTS)
- Lecture du contenu via **espeak-ng** (voix MBROLA `mb-fr7`), avec réglages vitesse/pitch/volume persistés dans `tts_config.json`.
- Utilisé notamment dans l'onglet **Concepts** (bouton 🔊 Lire le contenu / ⏹ Stop) pour l'explication pédagogique intégrée sur le fonctionnement des LLM.

### Onglet Concepts
- Page pédagogique intégrée expliquant les LLM, Ollama, les modèles disponibles et les précautions liées à l'usage d'un Raspberry Pi (refroidissement, montée en température).

### Vérification Ollama
- Au démarrage, l'application teste la disponibilité du service Ollama (`http://localhost:11434`) et affiche un avertissement s'il ne répond pas, tout en laissant l'interface utilisable.

## Lancement
```bash
python3 LLM_Raspberry_PI5.py
```

Ollama doit être démarré au préalable :
```bash
sudo systemctl start ollama
```

## Modèles Ollama à installer
```bash
ollama pull llama3.2:3b
ollama pull mistral:7b
ollama pull qwen2.5:7b
ollama pull deepseek-coder:6.7b
ollama pull gemma2:9b
ollama pull llama3.2-vision:11b
ollama pull moondream
```

## Dépendances Python
```bash
pip install requests pillow pdfminer.six --break-system-packages
```

- `espeak-ng` + voix MBROLA `mb-fr7` (lecture vocale — voir le projet [[espeak-tts]])

## Configuration TTS (`tts_config.json`)
Générée et mise à jour automatiquement par l'application ; exemple :
```json
{
  "enabled": false,
  "speed": 120,
  "pitch": 30,
  "volume": 100
}
```

## Structure du dépôt
```
LLM_Raspberry_PI5/
├── LLM_Raspberry_PI5.py     # Application principale (Tkinter)
├── tts_config.json          # Préférences TTS (généré à l'exécution)
├── historiques/             # Historiques de conversation par modèle, au format JSON (généré à l'exécution)
└── icons/                   # Logos des modèles et images d'illustration (non inclus ici)
```

> `tts_config.json` et le dossier `historiques/` sont propres à chaque installation/utilisateur et n'ont pas vocation à être versionnés (à adapter dans un `.gitignore`).

## Prérequis matériels
- Raspberry Pi 5 — 16 Go de RAM recommandés, SSD NVMe (les modèles quantifiés vont de 1,8 à 14 milliards de paramètres)
- Refroidissement actif recommandé (ventilateur, boîtier ventilé, dissipateur) : l'exécution de LLM sollicite fortement le CPU

## Auteur
Jean-François BRUNET - JFBConseils - Juillet 2026
