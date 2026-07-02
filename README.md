# ⬢ PolyKeep

Organiseur de fichiers 3D auto-hébergé pour **Unraid**. Scanne, prévisualise et
trie vos fichiers `.stl` et `.lys` avec un moteur de tri **sécurisé** (rien
n'est déplacé sans votre validation) et une visionneuse 3D interactive.

Inspiré de l'ergonomie de [Manyfold](https://manyfold.app), axé sur le tri
automatisé et la visualisation.

---

## ✨ Fonctionnalités

- **Scan & indexation** du dossier `/storage` (fichiers `.stl` et `.lys`).
- **Navigation par arborescence** : rail de dossiers pliable à gauche,
  fil d'Ariane cliquable, grille groupée par sous-dossier. Parfait pour les
  structures profondes et récursives.
- **Visionneuse 3D** Three.js (React Three Fiber) : rotation, zoom, auto-centrage
  des `.stl`. Pour les `.lys`, extraction de la vignette embarquée (aperçu image).
- **Moteur de tri intelligent** :
  - 🔁 **Détection des doublons** par hash SHA-256 (fichiers de même taille
    comparés en streaming).
  - 📁 **Regroupement par nom** : préfixe commun ou similarité (difflib).
  - 🏷️ **Tags automatiques** extraits du nom et du dossier parent
    (Warhammer, Articulated, Supporté…).
- **Tri sécurisé** : toutes les actions sont des *suggestions* à valider.
  La suppression est une mise en **corbeille** récupérable.
- **Persistance** SQLite dans `/config` (état du tri, tags, vignettes).
- **Thème sombre** style Unraid/Manyfold, interface responsive.

---

## 🧱 Stack technique

| Couche       | Technologie                                        |
| ------------ | -------------------------------------------------- |
| Backend      | Python 3.12 · FastAPI · SQLAlchemy · SQLite         |
| Frontend     | React 18 · Vite · React Three Fiber · @react-three/drei |
| Visionneuse  | Three.js (loader STL natif)                         |
| Déploiement  | Docker multi-stage, **un seul conteneur**           |

Un seul conteneur expose **tout** sur le port `8000` : l'API (`/api/*`) et le
frontend (servi en statique par FastAPI). Idéal pour Unraid.

---

## 🖥️ Interface

L'interface est organisée en trois colonnes :

```
┌──────────┬─────────────────────────────────┬──────────────┐
│ Dossiers │  Accueil › Imprimantes › Voron    │ Tri proposé  │
│ (arbre   │  📁 Crêtes (8)                    │              │
│  pliable) │   [carte] [carte] [carte] …      │  suggestions │
│          │  📁 Mods (4)                      │              │
│          │   [carte] [carte] …               │              │
└──────────┴─────────────────────────────────┴──────────────┘
```

- **Rail de dossiers** (gauche) : arbre de navigation pliable/déplié avec
  compteurs de fichiers. L'état d'expansion est conservé entre les sessions
  (`localStorage`). Un clic filtre la grille sur ce dossier et toute sa
  sous-arborescence.
- **Fil d'Ariane** : chemin cliquable au-dessus de la grille pour remonter
  rapidement à un dossier parent.
- **Grille groupée** : les fichiers sont automatiquement regroupés par
  sous-dossier direct avec des en-têtes `📁 Nom (count)`. Chaque carte affiche
  le chemin relatif du fichier pour le repérage dans les vues « tous ».
- **Panneau de tri** (droite) : suggestions de regroupement, doublons et
  déplacements, avec validation une par une.

Les filtres (recherche, statut, format, tags) s'appliquent **en plus** du
dossier sélectionné.

---

## 📁 Structure du projet

```
3d-view-web-app/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + montage du frontend
│   │   ├── config.py            # Config (env vars) + seuils
│   │   ├── database.py          # engine SQLAlchemy + session
│   │   ├── models.py            # File, Tag, FileTag, Suggestion, Setting
│   │   ├── schemas.py           # Pydantic v2
│   │   ├── routers/             # scan, files (+ /folders), sort, preview
│   │   └── services/            # scanner, hasher, tagger, grouper,
│   │                            #   lys_parser, sorter, paths
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Composant racine (état folder, filtres)
│   │   ├── components/
│   │   │   ├── FolderTree.jsx   # Arbre de navigation pliable
│   │   │   ├── Breadcrumb.jsx   # Fil d'Ariane cliquable
│   │   │   ├── FileGrid.jsx     # Grille groupée par sous-dossier
│   │   │   ├── FileCard.jsx     # Carte (thumb, nom, chemin, tags)
│   │   │   ├── Toolbar.jsx      # Barre de filtres (recherche, statut…)
│   │   │   ├── PreviewModal.jsx # Modal 3D + infos + actions
│   │   │   ├── SortPanel.jsx    # Suggestions de tri
│   │   │   └── StlViewer.jsx   # Visionneuse Three.js
│   │   ├── api/client.js        # client API (fetch)
│   │   ├── utils.js             # helpers (groupage, arbre, breadcrumb)
│   │   └── styles.css           # thème sombre
│   └── vite.config.js           # proxy dev → :8000
├── Dockerfile                   # build multi-stage (root context)
├── docker-compose.yml
└── .dockerignore
```

---

## 🚀 Démarrage rapide (Docker Compose)

### 1. Construire l'image

```bash
cd 3d-view-web-app
docker compose build
```

### 2. Lancer le conteneur

```bash
docker compose up -d
```

### 3. Ouvrir l'application

→ **http://IP-DU-SERVEUR:8000**

### 4. Premier scan

Cliquez sur **« ⏻ Scanner »**. L'app indexe vos fichiers récursivement dans
`/storage`, calcule les hashes (STL), extrait les vignettes (LYS) et génère les
suggestions de tri. Naviguez dans l'arbre de dossiers pour explorer vos
fichiers par emplacement.

---

## 🐳 Déploiement sur Unraid (pas-à-pas)

> Pré-requis : le plugin **Docker** (inclus par défaut) et le plugin
> **Compose Manager** (Community Applications) OU l'usage de l'interface web
> « Add Container » d'Unraid.

### Option A — Via Community Applications / Compose Manager (recommandé)

1. **Préparez vos partages** dans l'Unraid WebUI (`Main` → `Share`) :
   - `appdata/polykeep/config` (existe déjà si vous utilisez appdata)
   - Le partage contenant vos fichiers 3D, ex. `la_main_dans_le_sac`.

2. **Installez Compose Manager** :
   - `APPS` → cherchez *Compose* → installez *Compose.Manager*.

3. **Ajoutez le `docker-compose.yml`** :
   - Ouvrez Compose Manager → *New Stack* → nommez-la `polykeep`.
   - Collez le contenu de `docker-compose.yml` en **adaptant les chemins** :
     ```yaml
     volumes:
       - /mnt/user/appdata/polykeep/config:/config
       - /mnt/user/la_main_dans_le_sac:/storage:rw
     ```
   - Cliquez *Deploy* (Compose build l'image puis démarre).

### Option B — Via le template « Add Container » (mode manuel)

1. `Docker` → **Add container**.
2. Configurez :
   - **Repository** : image construite (`polykeep:latest`) ou build via CLI.
   - **Network type** : `Bridge`.
   - **Port** : `8000` (hôte) → `8000` (conteneur).
   - **Paths / Volumes** :
     | Conteneur | Hôte (exemple) |
     | --------- | ------------------ |
     | `/config` | `/mnt/user/appdata/polykeep/config` |
     | `/storage`| `/mnt/user/la_main_dans_le_sac` |
   - (Optionnel) **Variables** : voir *Configuration* ci-dessous.
3. **Apply**, puis ouvrez `http://IP:8000`.

### Volumes & persistance

| Montage | Rôle | Contenu |
| ------- | ---- | ------- |
| `/config` | Données d'état | `db.sqlite3`, `thumbnails/`, réglages |
| `/storage` | Vos fichiers 3D | Lecture **et** écriture (tri/déplacement) |

> ⚠️ Le conteneur **modifie** `/storage` (déplace, met à la corbeille). Toutes
> les opérations restent **à l'intérieur** de `/storage` (protection contre le
> path traversal). La corbeille est `/storage/.trash/<date>/`.

---

## ⚙️ Configuration (variables d'environnement)

Préfixe `T3D_`. Toutes sont optionnelles (valeurs par défaut indiquées).

| Variable | Défaut | Rôle |
| -------- | ------ | ---- |
| `T3D_CONFIG_DIR` | `/config` | Emplacement de la BDD |
| `T3D_STORAGE_DIR` | `/storage` | Dossier racine des fichiers |
| `T3D_SIMILARITY_THRESHOLD` | `0.6` | Seuil de similarité des noms (0–1) |
| `T3D_SCAN_WORKERS` | `0` | Workers pour hash/vignettes (`0` = auto, `1` = séquentiel) |
| `T3D_SORTED_SUBDIR` | `Trié` | Sous-dossier pour les fichiers triés |
| `T3D_ARCHIVED_SUBDIR` | `Archivé` | Sous-dossier d'archivage |
| `T3D_TRASH_SUBDIR` | `.trash` | Dossier corbeille (relatif à /storage) |
| `T3D_AUTO_KEYWORDS` | *(liste intégrée)* | Mots-clés pour les tags auto |

---

## 🔌 API REST

Documentation interactive : **http://IP:8000/docs** (Swagger UI).

| Méthode | Route | Description |
| ------- | ----- | ----------- |
| `GET`  | `/api/health` | État + nombre de fichiers |
| `POST` | `/api/scan` | Scan + recalcul des suggestions |
| `GET`  | `/api/files` | Liste filtrée (`?status=&tag=&q=&ext=&folder=&page=`) |
| `GET`  | `/api/folders` | Arborescence des dossiers (path + count) |
| `GET`  | `/api/files/{id}` | Détail d'un fichier |
| `POST` | `/api/files/{id}/move` | Déplacer (`{"target_dir": "Trié/…"}`) |
| `POST` | `/api/files/{id}/delete` | Mettre à la corbeille |
| `GET`  | `/api/preview/stl/{id}` | Flux binaire du STL |
| `GET`  | `/api/preview/lys/{id}` | Vignette extraite du .lys |
| `GET`  | `/api/suggestions` | Liste des suggestions (`?status=pending`) |
| `POST` | `/api/suggestions/recompute` | Recalculer |
| `POST` | `/api/suggestions/{id}/apply` | Appliquer |
| `POST` | `/api/suggestions/{id}/reject` | Rejeter |

Le paramètre `?folder=Imprimantes/Voron` filtre les fichiers de ce dossier **et**
de toute sa sous-arborescence de manière récursive. Omettre le paramètre
affiche tout.

---

## 🛠️ Développement local (hors Docker)

### Backend

```bash
cd backend
python -m venv .venv
# Windows : .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# Dossiers de travail locaux
set T3D_CONFIG_DIR=.devdata/config   # (Windows cmd)
set T3D_STORAGE_DIR=.devdata/storage

uvicorn app.main:app --reload --port 8000
```

### Frontend (hot-reload)

Dans un second terminal :

```bash
cd frontend
npm install
npm run dev
```

Vite sert le frontend sur `http://localhost:5173` et proxie les appels `/api`
vers le backend (`:8000`). À la fin du dev, `npm run build` régénère
`backend/static/`.

---

## 🔒 Sécurité

- **Path traversal bloqué** : tout chemin résolu est validé contre `/storage`
  (module `services/paths.py`).
- **Corbeille** : la suppression déplace vers `/storage/.trash/<date>/`
  (récupérable). Aucune suppression définitive n'existe dans l'UI.
- **Aucune exécution automatique** : déplacement/grouper/supprimer ne se font
  que sur validation explicite (suggestions puis « Appliquer »).
- **Lecture seule par défaut sur la BDD** côté front : seules les routes
  déclarées mutent des fichiers.

---

## ❓ Notes & limites

- **Format `.lys`** : propriétaire (Mango3D / Lychee Slicer), **sans
  spécification publique**. L'app tente d'extraire la **vignette** (le
  conteneur est souvent une archive ZIP). La **géométrie 3D n'est pas lue** :
  pour la prévisualisation 3D interactive, seul le **STL** est supporté.
- **Arborescences profondes** : le scan explore récursivement `/storage`
  (système `rglob`). Les dossiers cachés (`.trash`, `__pycache__`, etc.) sont
  ignorés automatiquement. L'arbre de navigation regroupe les fichiers par
  sous-dossier pour garder une vue claire même avec plusieurs niveaux
  d'imbrication.
- **Performance** : le hash SHA-256 est calculé en streaming (1 Mo/bloc) et
  seulement pour les fichiers de même taille. Les gros catalogues restent
  jouables ; un scan peut être relancé sans doublon de travail (les fichiers
  inchangés ne sont pas re-hachés).
- **Taille du bundle JS** : Three.js pèse ~1 Mo. Pour un usage perso ce n'est
  pas critique ; en cas de besoin, un *code-splitting* de la visionneuse via
  `React.lazy` réduirait le poids initial (optimisation non bloquante).

---

## 📜 Licence

Projet personnel — usage libre. Three.js, React et FastAPI gardent leurs
licences respectives (MIT / BSD).
