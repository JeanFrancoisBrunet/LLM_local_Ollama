#!/usr/bin/env python3
# =============================================================================
#  Interface LLM local – Raspberry Pi5 - 16 Go RAM et 256 Go SSD-NVMe
#  version intégrant :
#    Onglet Llama     : llama32-8k:latest | llama3.2:3b  (menu déroulant)
#    Onglet Mistral   : mistral:7b
#    Onglet Qwen      : Qwen 2.5 – 7B
#    Onglet DeepSeek  : DeepSeek‑Coder 6.7B
#    Onglet Gemma     : Gemma 2 – 9B
#    Onglet Vision    : Llama 3.2 Vision 11B (texte + images, Moondream intégré)
#  ainsi qu'un archivage des paramètres eSpeak & des historiques par modèle (JSON)
#
#  Auteur  : Jean‑François BRUNET - JFBConseils - Juin 2026
# =============================================================================

import tkinter as tk
from tkinter import ttk, filedialog
import threading
import base64
import json
import os
import requests
import subprocess
from datetime import datetime
from PIL import Image, ImageTk

# extraction PDF : nécessite pdfminer.six  (pip install pdfminer.six)
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("[PDF] pdfminer.six non installé – pip install pdfminer.six")

# ---------------------------------------------------------------------------
# Chemins et constantes
# ---------------------------------------------------------------------------
ICON_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
OLLAMA_URL = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Vérification de disponibilité d'Ollama (appelée au démarrage)
# ---------------------------------------------------------------------------
def check_ollama_available():
    """Retourne True si Ollama répond sur le port 11434, False sinon."""
    try:
        r = requests.get(OLLAMA_URL, timeout=3)
        return r.status_code == 200
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Moondream – modèle vision léger (questions en anglais uniquement)
# ---------------------------------------------------------------------------
MODEL_MOONDREAM = "moondream"
MOONDREAM_TEMPERATURE = 0.2   # analyse factuelle → faible variabilité

MOONDREAM_QUESTIONS = [
    ("🔍 Describe",       "Describe this image in detail."),
    ("👤 Who / What?",    "Who or what is the main subject of this image? Describe in detail."),
    ("📅 Time period?",   "What time period or era does this photo appear to be from? Explain why."),
    ("📝 Extract text",   "Extract and list all text visible in this image."),
    ("✨ One sentence",   "Write one single sentence that best captures the essence of this image."),
    ("🎨 Style / Colors", "Describe the colors, style, and artistic or photographic technique used."),
    ("📐 Layout",         "Describe the composition and spatial layout of this image."),
    ("❓ Custom…",        None),   # None = saisie libre
]

# Dossier de sauvegarde des historiques JSON (créé automatiquement)
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historiques")
os.makedirs(HISTORY_DIR, exist_ok=True)

# Nombre maximum de paires user/assistant conservées en mémoire active
# et nombre maximum de sessions archivées par fichier JSON.
# Ces deux constantes sont aussi exposées comme attributs de classe dans ChatTab.
MAX_HISTORY_PAIRS    = 10
MAX_HISTORY_SESSIONS = 20

# Timeout en secondes pour les appels http://localhost:11434 à Ollama (évite le blocage s'il ne répond pas)
REQUESTS_TIMEOUT = (10, None)   # (connect_timeout, read_timeout=infini pour le streaming)

THEMATIC_QUESTIONS = {
    "Analyse de documents": [
        "Explique-moi, simplement comme à un enfant de 10 ans, le texte en pièce jointe.",
        "Analyse le fichier en pièce jointe et résume-le.",
        "Analyse en détail… ",
        "Donne-moi les points essentiels du fichier en pièce jointe.",
        "Résume en 2 lignes ce texte : ",
        "Résume en 2 ou 3 lignes le document proposé.",
        "Résume en 2 paragraphes le document en pièce jointe.",
        "En tant qu'expert, rédige un résumé sous forme de points clés… ",
        "Sur quels faits s'appuie le document en pièce jointe ?",
        "Quels sont les principaux arguments du texte en pièce jointe ?",
        "Corrige et améliore ce texte : ",
        "Génère un plan détaillé à partir de ce document.",
        "Rédige thèse, antithèse et synthèse à partir du document joint.",
        "Reformule ce texte pour le rendre plus professionnel : ",
        "Traduis ce texte en anglais en conservant le style : ",
        "Traduis ce texte en français en conservant le style : "
    ],
    "Analyse d'images": [
        "Décris en quelques mots l'image en pièce jointe.",
        "Extrais et transcris le texte présent dans cette image."
    ],
    "Code & programmation": [
        "Génère un exemple de code Python pour : ",
        "Explique ce code et suggère des améliorations.",
        "Transpose ce code en algorithmique."
    ],
    "Résolution de problèmes": [
        "Résous ce problème de maths… ",
        "Résous l'équation suivante : ",
        "Comment puis-je résoudre simplement ce [problème] ?",
        "Propose 3 solutions alternatives à ce problème."
    ],
    "Autres": [
        "Propose-moi des idées pour… ",
        "Propose-moi une liste… ",
        "Raconte-moi une histoire courte sur… ",
        "Que dois-je faire pour… ?",
        "Parle-moi de… "
    ]
}

THEMATIC_ICONS = {
    "Analyse de documents": "doc.png",
    "Analyse d'images":     "image.png",
    "Code & programmation": "code.png",
    "Résolution de problèmes": "math.png",
    "Autres": "other.png"
}

# ---------------------------------------------------------------------------
# TTS MBROLA – lecture via espeak-ng (mb-fr7)
# ---------------------------------------------------------------------------
_tts_process = None   # processus espeak-ng en cours

def stop_tts():
    """Arrête la lecture TTS en cours, s'il y en a une."""
    global _tts_process
    if _tts_process and _tts_process.poll() is None:
        _tts_process.terminate()
        try:
            _tts_process.wait(timeout=1)
        except Exception:
            _tts_process.kill()
    _tts_process = None

def is_tts_running():
    """Renvoie True si une lecture est en cours."""
    return _tts_process is not None and _tts_process.poll() is None

def lire_texte_mbrola(text, root):
    global _tts_process
    try:
        text = (text or "").strip()
        if not text:
            return
        stop_tts()   # arrêt de toute lecture précédente
        speed  = root.tts_speed.get()  if hasattr(root, "tts_speed")  else 140
        pitch  = root.tts_pitch.get()  if hasattr(root, "tts_pitch")  else 30
        volume = root.tts_volume.get() if hasattr(root, "tts_volume") else 100
        cmd = [
            "espeak-ng",
            "-vmb-fr7",
            f"-s{speed}",
            f"-p{pitch}",
            f"-a{volume}",
            text,
        ]
        _tts_process = subprocess.Popen(cmd)
    except Exception as e:
        print(f"[TTS] Erreur lecture : {e}")

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def load_resized(path, w, h):
    try:
        img = Image.open(path)
        img.thumbnail((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"[IMG] Erreur chargement {path} : {e}")
        return None

MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 20 MB – au-delà Ollama rejette l'image

def encode_image_base64(path):
    """Encode une image en base64.
    Retourne (b64_str, None) en cas de succès, ou (None, message_erreur)."""
    try:
        size = os.path.getsize(path)
        if size > MAX_IMAGE_BYTES:
            return None, (
                f"[Image ignorée : {os.path.basename(path)} trop volumineuse "
                f"({size // (1024 * 1024)} MB > 20 MB)]"
            )
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), None
    except Exception as e:
        return None, f"[Erreur lecture image {os.path.basename(path)} : {e}]"

def read_text_file(path, max_chars=8000):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[Texte tronqué…]"
        return content
    except Exception as e:
        return f"[Impossible de lire le fichier : {path}]\n{e}"

def read_pdf_file(path, max_chars=8000):
    if not PDF_SUPPORT:
        return (
            "[PDF non lisible : pdfminer.six n'est pas installé.\n"
            "Installez-le avec : pip install pdfminer.six]"
        )
    try:
        content = pdf_extract_text(path)
        if not content or not content.strip():
            return "[PDF vide ou non lisible (PDF scanné sans OCR ?)]"
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[Texte tronqué…]"
        return content
    except Exception as e:
        return f"[Erreur extraction PDF : {path}]\n{e}"

def estimate_words(text):
    """Retourne le nombre de mots du texte (plus fiable qu'une estimation de tokens
    qui varie selon la langue et le contenu)."""
    return len(text.split())

# ---------------------------------------------------------------------------
# Classe d'un onglet de chat
# ---------------------------------------------------------------------------
class ChatTab:
    def __init__(self, parent, model_name, supports_vision, icon_file, root):
        self.parent         = parent
        self.model_name     = model_name
        self.supports_vision = supports_vision
        self.root           = root

        self.history        = []   # liste de {"role": ..., "content": ...}
        self.selected_files = []
        self._active_response = None   # connexion HTTP en cours (pour STOP)

        self.stream_buffer = ""
        self.stream_lock   = threading.Lock()
        self._msg_counter  = 0

        self._build_ui(icon_file)
        self._load_history()   # chargement de l'historique

    # -----------------------------------------------------------------------
    # Persistance de l'historique JSON
    # -----------------------------------------------------------------------
    def _history_path(self):
        """Retourne le chemin du fichier JSON pour ce modèle."""
        safe_name = self.model_name.replace(":", "_").replace("/", "_")
        return os.path.join(HISTORY_DIR, f"history_{safe_name}.json")

    def _load_history(self):
        """Charge l'historique depuis le fichier JSON et l'affiche dans le chat.
        Si le fichier est corrompu (ex. coupure courant pendant une écriture),
        il est renommé en .bak et l'historique repart à zéro plutôt que de crasher."""
        path = self._history_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                sessions = json.load(f)
        except json.JSONDecodeError as e:
            # Fichier corrompu → sauvegarde + repartir à zéro
            bak = path + ".bak"
            try:
                os.replace(path, bak)
            except Exception:
                pass
            print(f"[HISTORY] Fichier corrompu ({e}), renommé en {bak}")
            self.append_message(
                "system",
                f"[⚠️ Historique corrompu et mis de côté ({os.path.basename(bak)}). "
                "Nouvelle session démarrée proprement.]"
            )
            return
        except Exception as e:
            print(f"[HISTORY] Erreur chargement : {e}")
            return
        if not sessions:
            return
        self.append_message("system", f"── Historique chargé ({len(sessions)} session(s)) ──")
        for session in sessions:
            date = session.get("date", "")
            self.append_message("system", f"── Session du {date} ──")
            for msg in session.get("messages", []):
                self.append_message(msg["role"], msg["content"])
                self.history.append(msg)
        self.append_message("system", "── Fin de l'historique ──")

    def _save_history(self):
        """Sauvegarde la session courante dans le fichier JSON du modèle.
        Utilise une écriture atomique (fichier .tmp puis os.replace) pour éviter
        toute corruption si le programme ou le Pi est coupé pendant l'écriture.
        Les sessions les plus anciennes sont purgées au-delà du plafond."""
        path = self._history_path()
        tmp  = path + ".tmp"
        try:
            # Charger les sessions existantes
            sessions = []
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        sessions = json.load(f)
                except (json.JSONDecodeError, Exception):
                    sessions = []   # fichier illisible → on repart de zéro

            # Ajouter la session courante si elle contient des échanges
            if self.history:
                sessions.append({
                    "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "messages": list(self.history),
                })

            # Plafonner au nombre max de sessions (garder les plus récentes)
            if len(sessions) > MAX_HISTORY_SESSIONS:
                sessions = sessions[-MAX_HISTORY_SESSIONS:]

            # Écriture atomique : .tmp → fichier final (opération atomique sur Linux)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)   # atomique : pas de fichier corrompu possible

        except Exception as e:
            print(f"[HISTORY] Erreur sauvegarde : {e}")
            # Nettoyer le .tmp si l'écriture a échoué à mi-chemin
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _effacer_historique(self):
        """Efface l'historique et remet la zone de chat à zéro."""
        import tkinter.messagebox as mb
        if not mb.askyesno(
            "Effacer l'historique",
            f"Supprimer l'historique de {self.model_name} ?\n Cette action est irréversible.",
        ):
            return
        path = self._history_path()
        if os.path.exists(path):
            os.remove(path)
        self.history = []
        
        self.chat_text.delete("1.0", tk.END)
        
        self.append_message("system", "Historique effacé.")

    # -----------------------------------------------------------------------
    # Mise à jour dynamique du panneau d'informations modèle
    # -----------------------------------------------------------------------
    MODEL_INFO_DATA = {
        "llama3.2-vision": (
            "Llama 3.2 Vision\n\nDéc. 2023\n\n"
            "• Paramètres : 11 B\n• Taille : 7,8 GB\n"
            "• Multimodal : Texte…\n• Analyse d'images\n\n"
            "• Origine : Meta (USA)"
        ),
        "llama32-8k": (
            "Llama 3.2 (8K ctx)\n\n2024\n\n"
            "• Paramètres : 3 B\n• Taille : 2,0 GB\n"
            "• Contexte : 8 K\n• Compact & rapide\n\n"
            "• Origine : Meta (USA)"
        ),
        "llama3.2": (
            "Llama 3.2 3B\n\nSept. 2024\n\n"
            "• Paramètres : 3 B\n• Taille : 2,0 GB\n"
            "• Contexte : 128 K\n• Texte rapide\n"
            "• Léger & réactif\n\n• Origine : Meta (USA)"
        ),
        "moondream": (
            "Moondream\n\n2024\n\n"
            "• Paramètres : 1,8 B\n• Taille : ~1,1 GB\n"
            "• Vision spécialisée\n• Ultra-léger\n"
            "• ⚠️ English only\n\n• Origine : Vikhyat Kopf"
        ),
        "deepseek-coder": (
            "DeepSeek‑Coder\n\nDéc. 2023\n\n"
            "• Paramètres : 6.7 B\n• Taille : 3,8 GB\n"
            "• Spécialisé code\n• Python, C, JS\n"
            "• Analyse & correction\n\n• Origine : Chine"
        ),
        "qwen2.5": (
            "Qwen 2.5\n\nSept. 2024\n\n"
            "• Paramètres : 7 B\n• Taille : 4,7 GB\n"
            "• Généraliste\n• Raisonnement fiable\n"
            "• Multilingue (Français)\n\n• Origine : Chine"
        ),
        "mistral": (
            "Mistral 7B\n\nSept. 2023\n\n"
            "• Paramètres : 7 B\n• Taille : 4,4 GB\n"
            "• Contexte : 32 K\n• Rapide & concis\n"
            "• Français\n\n• Origine : France"
        ),
        "gemma2": (
            "Gemma 2\n\nJuin 2024\n\n"
            "• Paramètres : 9 B\n• Taille : 5,4 GB\n"
            "• Stable\n• Style naturel\n• Rédaction\n\n"
            "• Origine : Google (USA)"
        ),
    }

    def _get_model_info_text(self, model_name=None):
        """Retourne le texte d'info pour un modèle donné (ou self.model_name)."""
        name = model_name or self.model_name
        key  = name.split(":")[0]
        return self.MODEL_INFO_DATA.get(
            key,
            "Modèle local\n\nPoints forts :\n• LLM optimisé\n• Exécution locale\n• Raspberry Pi 5",
        )

    def _refresh_model_info(self):
        """Met à jour le Label d'info si l'attribut _info_label existe (onglets multi-modèles)."""
        if hasattr(self, "_info_label"):
            self._info_label.config(text=self._get_model_info_text())

    # -----------------------------------------------------------------------
    # Construction de l'interface
    # -----------------------------------------------------------------------
    def _build_ui(self, icon_file):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # === PARTIE HAUTE : Chat + Logo ===
        top_section = ttk.Frame(main_frame, height=450)
        top_section.pack(fill="both", expand=True)
        top_section.pack_propagate(True)

        # Zone chat à gauche
        chat_container = ttk.Frame(top_section)
        chat_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.chat_text = tk.Text(
            chat_container,
            wrap="word",
            bg="white",
            font=("Arial", 10),
            selectbackground="#0066ff",
            selectforeground="#ffffff",
            state="normal",
        )
        self.chat_text.pack(side="left", fill="both", expand=True)

        def _block_key(e):
            if e.state & 0x4:   # touche Control enfoncée → laisser passer
                return
            return "break"
        self.chat_text.bind("<Key>", _block_key)
        self.chat_text.bind("<Control-c>", lambda e: self._copy_from_chat())

        scrollbar = ttk.Scrollbar(chat_container, command=self.chat_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.chat_text.config(yscrollcommand=scrollbar.set)

        # Styles de balises
        self.chat_text.tag_config(
            "user",
            background="#e3f2fd", foreground="#000000",
            lmargin1=10, lmargin2=10, rmargin=80, spacing3=5,
        )
        self.chat_text.tag_config(
            "assistant",
            background="white", foreground="#000000",
            lmargin1=80, lmargin2=80, rmargin=10, spacing3=5,
        )
        self.chat_text.tag_config(
            "system", foreground="#777777", font=("Arial", 9, "italic")
        )
        self.chat_text.tag_config(
            "img_label",
            background="#e3f2fd", foreground="#0055cc",
            font=("Arial", 9, "italic"),
            lmargin1=10,
        )

        # Logo + informations modèle à droite
        logo_frame = ttk.Frame(top_section, width=180)
        logo_frame.pack(side="right", fill="y")
        logo_frame.pack_propagate(False)

        icon_path = os.path.join(ICON_DIR, icon_file)
        img = load_resized(icon_path, 120, 120)
        if img:
            self.logo_image = img
            ttk.Label(logo_frame, image=self.logo_image).pack(pady=8)
        else:
            ttk.Label(logo_frame, text="[LOGO]", font=("Arial", 16)).pack(pady=20)

        # Texte d'info centralisé dans MODEL_INFO_DATA (dict de classe)
        info_text = self._get_model_info_text()

        self._info_frame = ttk.LabelFrame(logo_frame, text="Informations", padding=5)
        self._info_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self._info_label = tk.Label(
            self._info_frame,
            text=info_text,
            justify="left",
            wraplength=150,
            font=("Arial", 9),
            bg="#f0f0f0",
        )
        self._info_label.pack(fill="both", expand=True)

        # === PARTIE BASSE : Contrôles ===

        # Fichiers joints
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill="x", pady=(10, 5))

        ttk.Button(file_frame, text="Ajouter fichiers",
                   command=self.ajouter_fichiers).pack(side="left")
        ttk.Button(file_frame, text="✕ Effacer fichiers",
                   command=self.effacer_fichiers).pack(side="left", padx=(5, 0))
        ttk.Button(file_frame, text="🗑 Effacer l'historique",
                   command=self._effacer_historique).pack(side="left", padx=(15, 0))
        self.label_files = ttk.Label(
            file_frame, text="Aucun fichier sélectionné", foreground="#666"
        )
        self.label_files.pack(side="left", padx=10)

        # Questions rapides
        faq_frame = ttk.LabelFrame(main_frame, text="Questions rapides", padding=5)
        faq_frame.pack(fill="x", pady=5)

        self.theme_icon_label = ttk.Label(faq_frame)
        self.theme_icon_label.grid(row=0, column=3, padx=10)

        self.category_var  = tk.StringVar()
        self.category_combo = ttk.Combobox(
            faq_frame,
            textvariable=self.category_var,
            values=list(THEMATIC_QUESTIONS.keys()),
            state="readonly",
        )
        self.category_combo.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.question_var  = tk.StringVar()
        self.question_combo = ttk.Combobox(
            faq_frame,
            textvariable=self.question_var,
            values=[],
            state="readonly",
            width=60,
        )
        self.question_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        def update_questions(event):
            cat = self.category_var.get()
            if cat in THEMATIC_QUESTIONS:
                self.question_combo["values"] = THEMATIC_QUESTIONS[cat]
                self.question_combo.set("")
            icon_file_name = THEMATIC_ICONS.get(cat)
            if icon_file_name:
                ip = os.path.join(ICON_DIR, icon_file_name)
                ic = load_resized(ip, 32, 32)
                if ic:
                    self.theme_icon_label.config(image=ic)
                    self.theme_icon_label.image = ic

        self.category_combo.bind("<<ComboboxSelected>>", update_questions)

        def insert_selected_question():
            q = self.question_var.get()
            if q:
                self.entry.delete("1.0", tk.END)
                self.entry.insert("1.0", q)
                self.entry.focus_set()

        ttk.Button(faq_frame, text="Insérer →",
                   command=insert_selected_question).grid(row=0, column=2, padx=5, pady=5)

        faq_frame.columnconfigure(0, weight=1)
        faq_frame.columnconfigure(1, weight=3)
        faq_frame.columnconfigure(2, weight=0)

        # --- Panneau Moondream (affiché AVANT la zone de saisie, onglet Vision 11B seulement) ---
        self._moondream_active = False
        if self.model_name == "llama3.2-vision:11b":
            self._build_moondream_panel(main_frame)

        # Saisie
        input_frame = ttk.LabelFrame(main_frame, text="Votre message", padding=5)
        input_frame.pack(fill="x", pady=5)

        left_input = ttk.Frame(input_frame)
        left_input.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.entry = tk.Text(left_input, height=3, font=("Arial", 11), wrap="word")
        self.entry.bind("<KeyRelease>", self.update_token_count)
        self.entry.pack(fill="x", expand=True)
        self.entry.bind("<Control-c>", lambda e: (self._copy_entry(), "break")[1])

        self.token_label = ttk.Label(left_input, text="Mots : 0", foreground="#555")
        self.token_label.pack(anchor="w", pady=(2, 0))

        btn_container = ttk.Frame(input_frame)
        btn_container.pack(side="right", fill="y")

        self.send_btn = ttk.Button(
            btn_container, text="Envoyer >>", command=self.on_send, width=12
        )
        self.send_btn.pack(fill="x", pady=(0, 4))

        self.stop_btn = tk.Button(
            btn_container,
            text="⏹ STOP",
            command=self.on_stop,
            width=12, height=2,
            fg="white", bg="red",
            activebackground="#aa0000", activeforeground="white",
            font=("Arial", 10, "bold"),
            relief="raised", bd=2,
        )
        self.stop_btn.pack(fill="x")
        self.stop_btn.config(state="disabled")

        self.stop_requested = False

        self.entry.bind("<Control-Return>", lambda e: self.on_send())
        self.entry.bind("<Return>", self._on_return)

        # Démarrage de la boucle de rafraîchissement du streaming
        self.root.after(50, self._refresh_stream)

    # -----------------------------------------------------------------------
    # Panneau Moondream (vision légère, anglais uniquement)
    # -----------------------------------------------------------------------
    def _build_moondream_panel(self, parent):
        """Crée le panneau Moondream sur une seule ligne compacte."""
        self._moon_frame = ttk.LabelFrame(
            parent,
            text="🌙 Moondream — Vision (⚠️ English only)",
            padding=(4, 2),
        )
        self._moon_frame.pack(fill="x", pady=(2, 2))

        # Toute l'UI sur une seule ligne horizontale
        row = ttk.Frame(self._moon_frame)
        row.pack(fill="x")

        # Bouton bascule
        self._moon_toggle_var = tk.StringVar(value="⬜ Activer")
        self._moon_toggle_btn = ttk.Button(
            row,
            textvariable=self._moon_toggle_var,
            command=self._toggle_moondream,
            width=12,
        )
        self._moon_toggle_btn.pack(side="left", padx=(0, 8))

        # Warning (visible uniquement quand Moondream actif)
        self._moon_warning = ttk.Label(
            row,
            text="",
            foreground="#cc6600",
            font=("Arial", 9, "italic"),
        )
        self._moon_warning.pack(side="left", padx=(0, 8))

        # Séparateur visuel + label
        ttk.Label(row, text="Question :").pack(side="left", padx=(0, 4))

        # Combo questions + bouton Insérer dans un sous-frame masqué initialement
        self._moon_q_var = tk.StringVar()
        q_labels = [lbl for lbl, _ in MOONDREAM_QUESTIONS]
        self._moon_extra = ttk.Frame(row)
        # (pack déclenché dans _toggle_moondream)

        self._moon_q_combo2 = ttk.Combobox(
            self._moon_extra,
            textvariable=self._moon_q_var,
            values=q_labels,
            state="readonly",
            width=22,
        )
        self._moon_q_combo2.pack(side="left", padx=(0, 4))

        ttk.Button(
            self._moon_extra,
            text="Insérer →",
            command=self._insert_moondream_question,
        ).pack(side="left", padx=(0, 8))

        ttk.Label(
            self._moon_extra,
            text="⤷ joindre une image puis Envoyer",
            foreground="#555",
            font=("Arial", 9, "italic"),
        ).pack(side="left")

    def _toggle_moondream(self):
        """Bascule entre mode Moondream et mode Llama Vision."""
        self._moondream_active = not self._moondream_active
        if self._moondream_active:
            self._moon_toggle_var.set("✅ Moondream")
            self._moon_warning.config(text="⚠️ English only")
            self._moon_extra.pack(side="left")
            self.append_message(
                "system",
                "[Moondream activé — question en anglais + joindre une image]",
            )
        else:
            self._moon_toggle_var.set("⬜ Activer")
            self._moon_warning.config(text="")
            self._moon_extra.pack_forget()
            self.append_message("system", "[Retour en mode Llama 3.2 Vision 11B]")

    def _insert_moondream_question(self):
        """Insère la question sélectionnée (en anglais) dans la zone de saisie."""
        label = self._moon_q_var.get()
        if not label:
            return
        # Récupère le prompt anglais correspondant
        prompt_en = next(
            (p for lbl, p in MOONDREAM_QUESTIONS if lbl == label), None
        )
        if prompt_en is None:
            # Cas "Custom…" : on vide juste le champ pour que l'utilisateur saisisse
            self.entry.delete("1.0", tk.END)
            self.entry.focus_set()
            return
        self.entry.delete("1.0", tk.END)
        self.entry.insert("1.0", prompt_en)
        self.entry.focus_set()

    # -----------------------------------------------------------------------
    # Raccourcis clavier et focus
    # -----------------------------------------------------------------------
    def _on_return(self, event):
        if event.state & 0x1:   # Shift+Entrée → nouvelle ligne
            return
        self.on_send()
        return "break"

    def set_focus(self):
        self.entry.focus_set()

    def insert_faq(self, text):
        self.entry.delete("1.0", tk.END)
        self.entry.insert("1.0", text)
        self.entry.focus_set()

    # -----------------------------------------------------------------------
    # Gestion des fichiers joints
    # -----------------------------------------------------------------------
    def ajouter_fichiers(self):
        files = filedialog.askopenfilenames(
            title="Choisir des fichiers",
            filetypes=[
                ("Documents", "*.txt *.pdf"),
                ("Images",    "*.jpg *.jpeg *.png"),
                ("Tous fichiers", "*.*"),
            ],
        )
        if files:
            self.selected_files = list(files)
            names = [os.path.basename(f) for f in files]
            # Couleur selon type : bleu=image, vert=texte/PDF, orange=mixte
            exts = {os.path.splitext(f)[1].lower() for f in files}
            img_exts = {".jpg", ".jpeg", ".png"}
            txt_exts = {".txt", ".pdf"}
            if exts <= img_exts:
                color = "#0055cc"   # bleu – image(s)
            elif exts <= txt_exts:
                color = "#007700"   # vert – texte/PDF
            else:
                color = "#cc6600"   # orange – mixte
            self.label_files.config(
                text="📎 " + ", ".join(names),
                foreground=color,
                font=("Arial", 9, "bold"),
            )
        else:
            self.selected_files = []
            self.label_files.config(
                text="Aucun fichier sélectionné",
                foreground="#666",
                font=("Arial", 9),
            )

    def effacer_fichiers(self):
        self.selected_files = []
        self.label_files.config(
            text="Aucun fichier sélectionné",
            foreground="#666",
            font=("Arial", 9),
        )

    # -----------------------------------------------------------------------
    # Miniature image dans la conversation
    # -----------------------------------------------------------------------
    def _insert_image_thumbnail(self, filepath):
        """Insère une miniature 120×120 de l'image dans le chat (côté utilisateur)."""
        try:
            img = Image.open(filepath)
            img.thumbnail((120, 120), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            # Garder une référence vivante pour éviter le garbage collector
            if not hasattr(self, "_thumb_refs"):
                self._thumb_refs = []
            self._thumb_refs.append(photo)

            name = os.path.basename(filepath)
            # Pas de state="disabled" ici : append_message doit pouvoir écrire après
            self.chat_text.insert("end", "    ")   # indentation côté utilisateur
            self.chat_text.image_create("end", image=photo, padx=4, pady=4)
            self.chat_text.insert("end", f"  🖼 {name}\n", "img_label")
            self.chat_text.see("end")
        except Exception as e:
            self.append_message("system", f"[Miniature non disponible : {e}]")

    # -----------------------------------------------------------------------
    # Affichage dans le widget de chat
    # -----------------------------------------------------------------------
    def append_message(self, role, text):
        
        if role == "user":
            tag, prefix = "user", "Vous : "
        elif role == "assistant":
            tag, prefix = "assistant", "LLM : "
        else:
            tag, prefix = "system", "[INFO] "
        self.chat_text.insert("end", prefix + text + "\n", tag)
        self.chat_text.see("end")
        

    def _insert_tts_link(self, full_text):
        """Insère un lien cliquable « 🔊 Lire ce message » après la réponse."""
        try:
            if not full_text or not full_text.strip():
                return
            self.chat_text.insert("end", "\n")
            tag = f"speak_link_{self._msg_counter}"
            self._msg_counter += 1
            self.chat_text.insert("end", "🔊 Lire ce message\n", (tag,))
            self.chat_text.tag_config(tag, foreground="#0066cc", underline=1)
            self.chat_text.tag_bind(
                tag, "<Button-1>",
                lambda e, t=full_text: lire_texte_mbrola(t, self.root)
            )
            self.chat_text.tag_bind(
                tag, "<Enter>",
                lambda e: self.chat_text.config(cursor="hand2")
            )
            self.chat_text.tag_bind(
                tag, "<Leave>",
                lambda e: self.chat_text.config(cursor="")
            )
            self.chat_text.see("end")
            # Lecture automatique si la case est cochée
            if hasattr(self.root, "tts_enabled") and self.root.tts_enabled.get():
                lire_texte_mbrola(full_text, self.root)
        except Exception as e:
            print(f"[TTS] Erreur insertion lien : {e}")

    # -----------------------------------------------------------------------
    # Buffer de streaming (thread → widget Tkinter via boucle after)
    # -----------------------------------------------------------------------
    def append_stream_chunk(self, text):
        with self.stream_lock:
            self.stream_buffer += text

    def _refresh_stream(self):
        # On vide le buffer SOUS le verrou dans une variable locale,
        # puis on insère dans Tkinter HORS du verrou.
        # Cela évite un deadlock si Tkinter rappelle un callback
        # qui tente d'acquérir stream_lock depuis le thread principal.
        with self.stream_lock:
            chunk = self.stream_buffer
            self.stream_buffer = ""
        if chunk:
            self.chat_text.insert("end", chunk, "assistant")
            self.chat_text.see("end")
        self.root.after(50, self._refresh_stream)

    # -----------------------------------------------------------------------
    # Copier / coller
    # -----------------------------------------------------------------------
    def _copy_from_chat(self):
        try:
            
            selection = self.chat_text.get("sel.first", "sel.last")
            
            self.root.clipboard_clear()
            self.root.clipboard_append(selection)
        except tk.TclError:
            pass

    def _copy_entry(self):
        try:
            text = self.entry.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass

    def _cut_entry(self):
        try:
            text = self.entry.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    # -----------------------------------------------------------------------
    # Compteur de tokens
    # -----------------------------------------------------------------------
    def update_token_count(self, event=None):
        text = self.entry.get("1.0", tk.END).strip()
        words = estimate_words(text)
        self.token_label.config(text=f"Mots : {words}")

    # -----------------------------------------------------------------------
    # Gestion de l'historique : troncature automatique
    # -----------------------------------------------------------------------
    def _trim_history(self):
        # On compte les paires complètes
        pairs = []
        i = 0
        while i < len(self.history) - 1:
            if (self.history[i]["role"] == "user"
                    and self.history[i + 1]["role"] == "assistant"):
                pairs.append((i, i + 1))
                i += 2
            else:
                i += 1
        if len(pairs) > MAX_HISTORY_PAIRS:
            # Nombre de paires à supprimer
            to_drop = len(pairs) - MAX_HISTORY_PAIRS
            # Index des messages à retirer (les plus anciens)
            drop_indices = set()
            for pair in pairs[:to_drop]:
                drop_indices.add(pair[0])
                drop_indices.add(pair[1])
            self.history = [
                msg for idx, msg in enumerate(self.history)
                if idx not in drop_indices
            ]

    # -----------------------------------------------------------------------
    # Envoi du message
    # -----------------------------------------------------------------------
    def on_send(self):
        prompt = self.entry.get("1.0", tk.END).strip()
        if not prompt:
            return

        self.append_message("user", prompt)
        self.entry.delete("1.0", tk.END)
        self.token_label.config(text="Tokens estimés : 0")

        files = list(self.selected_files)

        # Insérer les miniatures des images dans la conversation AVANT d'effacer
        for f in files:
            if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png"):
                self._insert_image_thumbnail(f)

        self.effacer_fichiers()

        self.send_btn.config(state="disabled", text="Envoi…")
        self.stop_btn.config(state="normal")
        # Synchroniser le bouton Stop de la barre de sélection (MultiModelChatTab)
        if hasattr(self, "_stop_btn_sel"):
            self._stop_btn_sel.config(state="normal")
        self.stop_requested = False

        threading.Thread(
            target=self._send_and_stream, args=(prompt, files), daemon=True
        ).start()

    def _send_and_stream(self, prompt, files):
        try:
            extra_text = ""
            images_b64 = []

            # Détermine si Moondream est actif sur cet onglet
            use_moondream = getattr(self, "_moondream_active", False)

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in (".jpg", ".jpeg", ".png") and (self.supports_vision or use_moondream):
                    b64, err = encode_image_base64(f)
                    if b64 is not None:
                        images_b64.append(b64)
                    else:
                        extra_text += f"\n{err}"
                elif ext == ".txt":
                    content    = read_text_file(f)
                    extra_text += (
                        f"\n\n[Contenu du fichier {os.path.basename(f)}]\n{content}\n"
                    )
                elif ext == ".pdf":
                    content    = read_pdf_file(f)
                    extra_text += (
                        f"\n\n[Contenu du fichier PDF {os.path.basename(f)}]\n{content}\n"
                    )
                else:
                    extra_text += f"\n\n[Fichier sélectionné : {f}]\n"

            full_user_text = prompt + extra_text

            self.history.append({"role": "user", "content": full_user_text})
            # Note : _trim_history() est appelé dans _finalize_response(),
            # après ajout de la réponse assistant, pour conserver des paires complètes.

            if use_moondream and images_b64:
                # Moondream : endpoint /api/generate, modèle fixe, temp basse
                self._stream_moondream(prompt, images_b64)
            elif self.supports_vision and images_b64:
                self._stream_generate_with_images(full_user_text, images_b64)
            else:
                self._stream_chat()

        finally:
            self.root.after(0, lambda: self.send_btn.config(state="normal", text="Envoyer >>"))
            self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
            if hasattr(self, "_stop_btn_sel"):
                self.root.after(0, lambda: self._stop_btn_sel.config(state="disabled"))

    # -----------------------------------------------------------------------
    # Streaming commun : traite une réponse HTTP en flux
    # -----------------------------------------------------------------------
    def _process_stream(self, response, content_key):
        assistant_text = ""
        self.root.after(0, lambda: self.append_message("assistant", ""))
        self._active_response = response

        try:
            for line in response.iter_lines():
                if self.stop_requested:
                    response.close()
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                if content_key == "content":
                    delta = data.get("message", {}).get("content", "")
                else:
                    delta = data.get("response", "")

                if delta:
                    assistant_text += delta
                    self.root.after(0, lambda d=delta: self.append_stream_chunk(d))

        except requests.exceptions.ChunkedEncodingError:
            # Connexion fermée proprement par on_stop → sortie silencieuse
            if not self.stop_requested:
                raise
        except Exception:
            # Autre erreur (JSON malformé inattendu, perte réseau…) → remontée
            if not self.stop_requested:
                raise
        finally:
            self._active_response = None

        return assistant_text

    def _finalize_response(self, assistant_text):
        if assistant_text.strip():
            self.history.append({"role": "assistant", "content": assistant_text})
            # Troncature APRÈS la paire complète user+assistant → pas de message
            # utilisateur orphelin envoyé au modèle sans réponse correspondante.
            self._trim_history()
            self._save_history()   # sauvegarde après chaque réponse complète

            # Tous les accès au widget chat_text passent par root.after()
            # car _finalize_response s'exécute depuis le thread secondaire.
            words = estimate_words(assistant_text)
            self.root.after(0, lambda: self.chat_text.insert("end", "\n"))
            self.root.after(
                0, lambda: self.append_message("system", f"[>>> Réponse : {words} mots]")
            )
            self.root.after(0, lambda t=assistant_text: self._insert_tts_link(t))

    # -----------------------------------------------------------------------
    # Méthode commune de streaming – factorise _stream_chat / vision / moondream
    # -----------------------------------------------------------------------
    def _do_stream(self, payload, error_label="API"):
        """Envoie payload à /api/chat, streame la réponse et finalise.
        Parameters
        ----------
        payload     : dict  – corps JSON de la requête Ollama
        error_label : str   – libellé affiché dans le message d'erreur
        """
        try:
            with requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                stream=True,
                timeout=REQUESTS_TIMEOUT,
            ) as r:
                r.raise_for_status()
                assistant_text = self._process_stream(r, "content")

            if not self.stop_requested:
                self._finalize_response(assistant_text)

        except requests.exceptions.Timeout:
            self.root.after(
                0, lambda: self.append_message("system", "[Connexion Ollama trop lente — réessayez]")
            )
        except Exception as e:
            if not self.stop_requested:
                self.root.after(
                    0,
                    lambda err=str(e): self.append_message(
                        "system", f"[Erreur {error_label} : {err}]"
                    ),
                )

    # -----------------------------------------------------------------------
    # Streaming texte – endpoint /api/chat
    # -----------------------------------------------------------------------
    def _stream_chat(self):
        payload = {
            "model":    self.model_name,
            "messages": self.history,
            "stream":   True,
        }
        self._do_stream(payload, error_label="API chat")

    # -----------------------------------------------------------------------
    # Streaming vision – Llama 3.2 Vision (images dans le message courant seulement)
    # -----------------------------------------------------------------------
    def _stream_generate_with_images(self, user_text, images_b64):
        """Llama Vision : /api/chat avec l'image uniquement dans le message courant.
        Llama 3.2 Vision ne supporte pas les images dans l'historique —
        on envoie seulement le message utilisateur actuel."""
        payload = {
            "model":   self.model_name,
            "messages": [
                {
                    "role":    "user",
                    "content": user_text,
                    "images":  images_b64,
                }
            ],
            "stream": True,
        }
        self._do_stream(payload, error_label="API vision")

    # -----------------------------------------------------------------------
    # Streaming Moondream – modèle vision léger, Qualité (température) basse
    # -----------------------------------------------------------------------
    def _stream_moondream(self, prompt_en, images_b64):
        """Moondream : /api/chat avec images dans le message courant uniquement.
        Qualité basse pour analyse factuelle."""
        payload = {
            "model":   MODEL_MOONDREAM,
            "messages": [
                {
                    "role":    "user",
                    "content": prompt_en,
                    "images":  images_b64,
                }
            ],
            "stream":  True,
            "options": {
                "temperature": MOONDREAM_TEMPERATURE,
                "num_predict": 512,
            },
        }
        self._do_stream(payload, error_label="Moondream")

    # -----------------------------------------------------------------------
    # Arrêt de la génération
    # -----------------------------------------------------------------------
    def on_stop(self):
        self.stop_requested = True

        # 1. Fermer la connexion HTTP Python (sort de iter_lines proprement)
        resp = getattr(self, "_active_response", None)
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

        # 2. Tuer le runner Ollama qui calcule en arrière-plan
        #    "ollama stop" ne suffit pas — on tue le processus directement
        #    puis on redémarre le serveur Ollama pour les requêtes suivantes
        def _kill_and_restart():
            try:
                import time
                # Les runners appartiennent à l'user "ollama" → sudo obligatoire.
                # NOPASSWD requis dans sudoers pour ces commandes (voir README).
                r1 = subprocess.run(
                    ["sudo", "pkill", "-SIGTERM", "-f", "ollama runner"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                time.sleep(1.0)
                r2 = subprocess.run(
                    ["sudo", "pkill", "-SIGKILL", "-f", "ollama runner"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                # pkill retourne 1 si aucun processus trouvé (pas une vraie erreur),
                # mais retourne 126/127 si sudo échoue (permission refusée).
                sudo_failed = any(
                    r.returncode in (126, 127) for r in (r1, r2)
                )
                if sudo_failed:
                    self.root.after(0, lambda: self.append_message(
                        "system",
                        "[⚠️ STOP partiel : sudo pkill refusé — "
                        "la génération CPU continue peut-être en arrière-plan. "
                        "Vérifiez la règle NOPASSWD dans /etc/sudoers.]"
                    ))
                    print(f"[STOP] sudo pkill stderr: {r1.stderr} / {r2.stderr}")
                    return   # on ne tente pas le restart si sudo est bloqué

                time.sleep(0.5)
                # Redémarre le service proprement via systemd
                r3 = subprocess.run(
                    ["sudo", "systemctl", "restart", "ollama"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                if r3.returncode not in (0, 1):
                    self.root.after(0, lambda: self.append_message(
                        "system",
                        f"[⚠️ Redémarrage Ollama incertain (code {r3.returncode}). "
                        "Si la prochaine requête échoue, relancez Ollama manuellement.]"
                    ))
                    print(f"[STOP] systemctl restart stderr: {r3.stderr}")
            except Exception as e:
                print(f"[STOP] kill/restart échoué : {e}")
                self.root.after(0, lambda: self.append_message(
                    "system", f"[⚠️ STOP : exception inattendue ({e})]"
                ))

        threading.Thread(target=_kill_and_restart, daemon=True).start()

        self.root.after(0, lambda: self.send_btn.config(state="normal", text="Envoyer >>"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        if hasattr(self, "_stop_btn_sel"):
            self.root.after(0, lambda: self._stop_btn_sel.config(state="disabled"))
        self.root.after(0, lambda: self.append_message(
            "system", "[⛔ Génération arrêtée — CPU libéré]"
        ))

# ---------------------------------------------------------------------------
# Onglet multi-modèles avec sélection par menu déroulant
# ---------------------------------------------------------------------------
class MultiModelChatTab(ChatTab):
    """ChatTab étendu avec un sélecteur de modèle (Combobox) en haut de l'onglet.
    models_list : liste de tuples (label_affichage, model_id_ollama)
    default_index : index du modèle sélectionné par défaut (0 = premier)"""

    def __init__(self, parent, models_list, supports_vision, icon_file, root,
                 default_index=0):
        self._models_list   = models_list   # [(label, model_id), ...]
        self._default_index = default_index

        # On initialise ChatTab avec le modèle par défaut
        default_model = models_list[default_index][1]
        super().__init__(
            parent,
            model_name=default_model,
            supports_vision=supports_vision,
            icon_file=icon_file,
            root=root,
        )

    # ------------------------------------------------------------------
    # Surcharge de _build_ui : on insère la barre de sélection en PREMIER
    # puis on appelle le build standard (qui pack-fera le reste en dessous)
    # ------------------------------------------------------------------
    def _build_ui(self, icon_file):
        """On construit d'abord la barre de sélection, puis l'UI normale."""
        # Barre de sélection du modèle
        self._sel_frame = ttk.LabelFrame(self.parent, text="Modèle sélectionné", padding=4)
        self._sel_frame.pack(fill="x", padx=10, pady=(8, 0))

        labels = [lbl for lbl, _ in self._models_list]

        ttk.Label(self._sel_frame, text="Choisir le modèle :").pack(side="left", padx=(0, 8))

        self._model_var = tk.StringVar(value=labels[self._default_index])
        self._model_combo = ttk.Combobox(
            self._sel_frame,
            textvariable=self._model_var,
            values=labels,
            state="readonly",
            width=40,
        )
        self._model_combo.pack(side="left")
        self._model_combo.bind("<<ComboboxSelected>>", self._on_model_change)

        # Indicateur du modèle actif
        self._active_label = ttk.Label(
            self._sel_frame,
            text=f"▶ actif : {self._models_list[self._default_index][1]}",
            foreground="#006600",
            font=("Arial", 9, "italic"),
        )
        self._active_label.pack(side="left", padx=(12, 0))

        # 2nd Bouton STOP ancré à droite dans la barre de sélection
        self._stop_btn_sel = tk.Button(
            self._sel_frame,
            text="⏹ STOP",
            command=lambda: self.on_stop(),
            fg="white", bg="red",
            activebackground="#aa0000", activeforeground="white",
            font=("Arial", 9, "bold"),
            relief="raised", bd=2,
            state="disabled",
        )
        self._stop_btn_sel.pack(side="right", padx=(0, 6), pady=2)

        # Construction de l'UI ChatTab standard (qui pack dans self.parent)
        super()._build_ui(icon_file)

    def _on_model_change(self, event=None):
        """Appelé quand l'utilisateur change de modèle dans le Combobox."""
        label    = self._model_var.get()
        model_id = next(mid for lbl, mid in self._models_list if lbl == label)

        # Sauvegarder l'historique de l'ancien modèle
        self._save_history()

        # Changer de modèle
        self.model_name = model_id
        self.history    = []

        self._active_label.config(text=f"▶ actif : {model_id}")

        # Mettre à jour le panneau d'informations
        self._refresh_model_info()

        # Recharger l'historique du nouveau modèle
        self._load_history()

        self.append_message(
            "system",
            f"[Modèle changé → {model_id}]",
        )

    def _history_path(self):
        """Chemin JSON basé sur le model_name courant (dynamique)."""
        safe_name = self.model_name.replace(":", "_").replace("/", "_")
        return os.path.join(HISTORY_DIR, f"history_{safe_name}.json")

# ---------------------------------------------------------------------------
# Classe GUI principale
# ---------------------------------------------------------------------------
class LLMGUI:
    TTS_CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tts_config.json"
    )

    def __init__(self, root):
        self.root = root
        self.root.title("Pilotage local LLM – Raspberry Pi 5")
        self.root.geometry("1200x950")
        self.root.minsize(1000, 900)

        # --- Chargement de la config TTS persistante ---
        tts_cfg = self._load_tts_config()

        # Barre TTS
        tts_frame = ttk.LabelFrame(self.root, text="TTS MBROLA")
        tts_frame.pack(fill="x", padx=10, pady=5)

        self.tts_enabled = tk.BooleanVar(value=tts_cfg.get("enabled", False))
        ttk.Checkbutton(
            tts_frame, text="🔊 Lecture auto", variable=self.tts_enabled
        ).grid(row=0, column=0, padx=5, sticky="w")

        self.tts_speed  = tk.IntVar(value=tts_cfg.get("speed",  140))
        self.tts_pitch  = tk.IntVar(value=tts_cfg.get("pitch",   30))
        self.tts_volume = tk.IntVar(value=tts_cfg.get("volume", 100))

        # Titres + valeur numérique sur la même ligne (row=0)
        ttk.Label(tts_frame, text="Mots/min :").grid(row=0, column=1, sticky="e")
        lbl_speed  = ttk.Label(tts_frame, text=str(self.tts_speed.get()),  width=4, anchor="w")
        lbl_speed.grid(row=0, column=2, sticky="w", padx=(0, 15))

        ttk.Label(tts_frame, text="Pitch :").grid(row=0, column=3, sticky="e")
        lbl_pitch  = ttk.Label(tts_frame, text=str(self.tts_pitch.get()),  width=4, anchor="w")
        lbl_pitch.grid(row=0, column=4, sticky="w", padx=(0, 15))

        ttk.Label(tts_frame, text="Volume (%) :").grid(row=0, column=5, sticky="e")
        lbl_volume = ttk.Label(tts_frame, text=str(self.tts_volume.get()), width=4, anchor="w")
        lbl_volume.grid(row=0, column=6, sticky="w")

        def _update_speed(*_):
            lbl_speed.config(text=str(self.tts_speed.get()))
            self._save_tts_config()
        def _update_pitch(*_):
            lbl_pitch.config(text=str(self.tts_pitch.get()))
            self._save_tts_config()
        def _update_volume(*_):
            lbl_volume.config(text=str(self.tts_volume.get()))
            self._save_tts_config()

        self.tts_speed.trace_add("write",  _update_speed)
        self.tts_pitch.trace_add("write",  _update_pitch)
        self.tts_volume.trace_add("write", _update_volume)
        self.tts_enabled.trace_add("write", lambda *_: self._save_tts_config())

        ttk.Scale(tts_frame, from_=80,  to=250, orient="horizontal",
                  variable=self.tts_speed,  length=120).grid(row=1, column=1, columnspan=2, padx=5, sticky="w")
        ttk.Scale(tts_frame, from_=0,   to=99,  orient="horizontal",
                  variable=self.tts_pitch,  length=120).grid(row=1, column=3, columnspan=2, padx=5, sticky="w")
        ttk.Scale(tts_frame, from_=0,   to=200, orient="horizontal",
                  variable=self.tts_volume, length=120).grid(row=1, column=5, columnspan=2, padx=5, sticky="w")

        # Exposer les variables TTS sur root pour que les ChatTab y accèdent
        self.root.tts_enabled = self.tts_enabled
        self.root.tts_speed   = self.tts_speed
        self.root.tts_pitch   = self.tts_pitch
        self.root.tts_volume  = self.tts_volume

        # Notebook principal
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill="both", padx=10, pady=10)

        # --- Définition des onglets ---
        # Ordre : Llama | Mistral | Qwen | DeepSeek | Gemma | Vision | Concepts
        tab_llamas   = ttk.Frame(notebook)   # 0 – Famille Llama (multi-modèles)
        tab_mistrals = ttk.Frame(notebook)   # 1 – Mistral 7B
        tab_qwen     = ttk.Frame(notebook)   # 2 – Qwen 2.5 7B
        tab_deepseek = ttk.Frame(notebook)   # 3 – DeepSeek-Coder
        tab_gemma    = ttk.Frame(notebook)   # 4 – Gemma 2
        tab_llama    = ttk.Frame(notebook)   # 5 – Vision 11B
        tab_concepts = ttk.Frame(notebook)   # 6 – Concepts

        notebook.add(tab_llamas,   text="🦙 Llama")
        notebook.add(tab_mistrals, text="🌬 Mistral")
        notebook.add(tab_qwen,     text="Qwen 2.5 – 7B")
        notebook.add(tab_deepseek, text="DeepSeek‑Coder")
        notebook.add(tab_gemma,    text="Gemma 2 – 9B")
        notebook.add(tab_llama,    text="🦙 Vision 11B")
        notebook.add(tab_concepts, text="Concepts")
        self.concepts_tab = tab_concepts

        # --- Onglet Vision (onglet dédié) ---
        self.llama_tab = ChatTab(
            tab_llama,    model_name="llama3.2-vision:11b",
            supports_vision=True,  icon_file="ollama.png",   root=self.root,
        )

        # --- Onglet Llama (multi-modèles) ---
        # Nota : llama3.2-vision:11b est accessible dans l'onglet Vision uniquement.
        LLAMA_MODELS = [
            ("llama32-8k:latest  – 2,0 GB  | ctx  8K",  "llama32-8k:latest"),
            ("llama3.2:3b        – 2,0 GB  | ctx 128K", "llama3.2:3b"),
        ]
        self.llamas_tab = MultiModelChatTab(
            tab_llamas,
            models_list=LLAMA_MODELS,
            supports_vision=False,
            icon_file="ollama.png",
            root=self.root,
            default_index=0,   # llama32-8k:latest par défaut
        )

        # --- Onglets LLM ---
        self.mistrals_tab = ChatTab(
            tab_mistrals, model_name="mistral:7b",
            supports_vision=False, icon_file="mistral.png", root=self.root,
        )
        self.qwen_tab = ChatTab(
            tab_qwen,     model_name="qwen2.5:7b",
            supports_vision=False, icon_file="qwen2.5.png",  root=self.root,
        )
        self.deepseek_tab = ChatTab(
            tab_deepseek, model_name="deepseek-coder:6.7b",
            supports_vision=False, icon_file="deepseek.png", root=self.root,
        )
        self.gemma_tab = ChatTab(
            tab_gemma,    model_name="gemma2:9b",
            supports_vision=False, icon_file="gemma.png",    root=self.root,
        )

        # Onglet Concepts
        self._build_concepts_tab(tab_concepts)

        # Index de l'onglet Vision (5)
        VISION_TAB_IDX = 5

        def _on_tab_changed(event):
            """Ajuste la hauteur de fenêtre selon l'onglet actif."""
            selected = notebook.index(notebook.select())
            h = 900 if selected == VISION_TAB_IDX else (950 if selected == 0 else 800)
            w = self.root.winfo_width()
            self.root.geometry(f"{w}x{h}")
            self.root.minsize(1000, h - 50 if h > 800 else 750)

        notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)

    def _load_tts_config(self):
        """Charge la config TTS depuis tts_config.json."""
        try:
            if os.path.exists(self.TTS_CONFIG_PATH):
                with open(self.TTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[TTS] Erreur chargement config : {e}")
        return {}

    def _save_tts_config(self):
        """Sauvegarde la config TTS dans tts_config.json."""
        try:
            cfg = {
                "enabled": self.tts_enabled.get(),
                "speed":   self.tts_speed.get(),
                "pitch":   self.tts_pitch.get(),
                "volume":  self.tts_volume.get(),
            }
            with open(self.TTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TTS] Erreur sauvegarde config : {e}")

    def _toggle_concepts_tts(self, text_widget):
        """Bascule Lire / Stop pour l'onglet Concepts, et surveille la fin."""
        if is_tts_running():
            stop_tts()
            self._concepts_btn_var.set("🔊 Lire le contenu")
        else:
            lire_texte_mbrola(text_widget.get("1.0", tk.END), self.root)
            self._concepts_btn_var.set("⏹ Stop")
            self._watch_concepts_tts()

    def _watch_concepts_tts(self):
        """Repasse le bouton en 'Lire' dès que la lecture se termine naturellement."""
        if is_tts_running():
            self.root.after(300, self._watch_concepts_tts)
        else:
            self._concepts_btn_var.set("🔊 Lire le contenu")

    # -----------------------------------------------------------------------
    # Onglet Concepts
    # -----------------------------------------------------------------------
    def _build_concepts_tab(self, parent):
        concepts_frame = ttk.Frame(parent)
        concepts_frame.pack(fill="both", expand=True, padx=20, pady=20)

        concepts_text = tk.Text(
            concepts_frame, wrap="word", font=("Arial", 11), bg="white", height=25
        )
        concepts_text.pack(side="left", fill="both", expand=True)

        resume = """\
Introduction aux LLM sur Raspberry Pi 5 - L'intelligence artificielle (IA) a connu des avancées fulgurantes
ces dernières années. Les modèles LLM (Large Language Model) sont désormais capables de comprendre et de 
générer du texte, d'analyser des images,de résumer des documents ou encore de traduire des contenus.
Toutefois, la dépendance aux services cloud soulève des questions de confidentialité, de souveraineté et de contrôle des données.

Une alternative consiste à exécuter ces modèles localement, grâce à un outil open‑source comme Ollama (sous
Linux). Ollama permet de faire tourner des LLM directement sur une machine personnelle, offrant ainsi une 
maîtrise totale des données, une meilleure confidentialité et une grande flexibilité dans le choix des modèles.

Qu'est‑ce qu'un LLM ? C'est un modèle d'IA entraîné sur d'immenses quantités de texte. Il peut :
    • répondre à des questions,
    • compléter ou générer du texte, résumer des documents, traduire, classer des contenus,
    • créer des embeddings (représentations vectorielles du sens des textes),
    • analyser des images, de l'audio ou de la vidéo selon les modèles.

Ollama permet de charger différents modèles selon les besoins, chacun offrant des capacités spécifiques.

Modèles disponibles dans cette interface :
    • Famille Llama (onglet avec sélecteur) :
        – llama32-8k:latest  ⚡ contexte  8K,  2,0 GB  (compact, réponses rapides)
        – llama3.2:3b        ⚡ contexte 128K, 2,0 GB  (polyvalent, très rapide)
    • Mistral 7B — contexte 32K, 4,4 GB (généraliste, bon équilibre vitesse/qualité)
    • Qwen 2.5 7B — généraliste multilingue, raisonnement (Alibaba, 4,7 GB, ctx 128K)
    • DeepSeek‑Coder 6.7B — spécialisé Python / C / JS (3,8 GB, ctx 16K)
    • Gemma 2 9B — rédaction naturelle, style fluide (Google, 5,4 GB, ctx 8K)
    • Llama 3.2 Vision 11B — multimodal texte + images (Meta, 7,8 GB, ctx 128K)
        ↳ Moondream intégré — vision ultra-rapide ⚠️ anglais uniquement (1,7 GB)

Pourquoi utiliser un Raspberry Pi ? Dans sa version 16 Go de RAM, il est suffisamment puissant pour exécuter
localement des modèles quantifiés de 1,8B à 14B de paramètres. Cela permet :
   • d'utiliser l'IA sans connexion cloud,
   • de réduire la consommation énergétique,
   • de disposer d'une plateforme compacte, silencieuse et économique.

Cependant, l'exécution de modèles LLM sollicite fortement le CPU. Cela peut entraîner une montée en 
température importante. Il est donc essentiel de prévoir :
    • un refroidissement actif (ventilateur, boîtier ventilé, dissipateur),
    • un suivi de la température en temps réel pour éviter la surchauffe et le throttling.
"""
        concepts_text.insert("1.0", resume)
        concepts_text.tag_configure("title", font=("Arial", 11, "bold", "underline"))

        def format_title(word):
            start = "1.0"
            while True:
                pos = concepts_text.search(word, start, tk.END)
                if not pos:
                    break
                end = f"{pos}+{len(word)}c"
                concepts_text.tag_add("title", pos, end)
                start = end

        for title in [
            "Introduction aux LLM",
            #"intelligence artificielle (IA)",
            #"LLM",
            #"Ollama",
        ]:
            format_title(title)
        concepts_text.config(state="disabled")

        # Bouton Lire/Stop pour l'onglet Concepts
        self._concepts_btn_var = tk.StringVar(value="🔊 Lire le contenu")
        self._concepts_btn = ttk.Button(
            concepts_frame,
            textvariable=self._concepts_btn_var,
            command=lambda: self._toggle_concepts_tts(concepts_text),
        )
        self._concepts_btn.pack(pady=(10, 0), anchor="w")

        img_frame = ttk.Frame(concepts_frame, width=200)
        img_frame.pack(side="right", fill="y")
        img_frame.pack_propagate(False)

        img_path = os.path.join(ICON_DIR, "RPI5_ventilateur.png")
        img = load_resized(img_path, 180, 180)
        if img:
            lbl = ttk.Label(img_frame, image=img)
            lbl.image = img
            lbl.pack(pady=20)

# ---------------------------------------------------------------------------
# Splash Screen
# ---------------------------------------------------------------------------
def show_splash(root, callback):
    splash = tk.Toplevel(root)
    splash.title("LLM…")
    splash.geometry("250x200")
    splash.resizable(False, False)

    splash.update_idletasks()
    x = (splash.winfo_screenwidth()  // 2) - 175
    y = (splash.winfo_screenheight() // 2) - 100
    splash.geometry(f"250x200+{x}+{y}")
    splash.attributes("-topmost", True)

    icon_path = os.path.join(ICON_DIR, "Large-Language-Model.png")
    try:
        img = Image.open(icon_path).resize((250, 180))
        splash_img = ImageTk.PhotoImage(img)
        tk.Label(splash, image=splash_img).pack(pady=10)
        splash.image_ref = splash_img
    except Exception as e:
        print(f"[SPLASH] Erreur image : {e}")
        tk.Label(splash, text="🤖 LLM Interface", font=("Arial", 24, "bold")).pack(pady=30)

    tk.Label(splash, text="Chargement de l'interface LLM…", font=("Arial", 11)).pack()

    root.after(2000, lambda: (splash.destroy(), callback()))

# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    root.withdraw()

    def start_gui():
        root.deiconify()
        gui = LLMGUI(root)
        # Vérification Ollama après construction de l'UI (les onglets existent)
        if not check_ollama_available():
            import tkinter.messagebox as mb
            mb.showwarning(
                "Ollama non disponible",
                "⚠️  Ollama ne répond pas sur http://localhost:11434\n\n"
                "Vérifiez que le service est démarré :\n"
                "  sudo systemctl start ollama\n\n"
                "L'interface reste ouverte mais les requêtes échoueront."
            )

    show_splash(root, start_gui)
    root.mainloop()

if __name__ == "__main__":
    main()
