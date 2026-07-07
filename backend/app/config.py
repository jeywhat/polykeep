"""Application configuration.

All paths and tunable settings are loaded from environment variables so the
same image runs identically in local dev and on the Unraid container.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="T3D_", env_file=".env", extra="ignore")

    # --- Paths (Docker volume mounts) -------------------------------------
    config_dir: Path = Path("/config")
    storage_dir: Path = Path("/storage")

    # --- Tunables for the sort engine -------------------------------------
    similarity_threshold: float = 0.6  # difflib ratio above which two file
    # names are considered "related"
    scan_workers: int = 0  # 0 = auto, 1 = sequential, >1 = parallel extras

    # Supported 3D file extensions (comma-separated, with dots)
    # Default: STL, LYS, OBJ, PLY, 3MF, GLTF, GLB, FBX, DAE, STL, AMF
    supported_extensions: str = (
        ".stl,.lys,.obj,.ply,.3mf,.gltf,.glb,.fbx,.dae,.amf"
    )

    auto_keywords: str = (
        "warhammer,wh40k,age of sigmar,aos,dnd,d&d,articulated,articule,"
        "supported,supporte,support,no_support,no-support,sans_support,"
        "miniature,mini,figurine,terrain,scatter,building,vehicle,character,"
        "hero,monster,beast,demon,daemon,space marine,eldar,ork,tyranid,"
        "necron,chaos,imperial,primaris"
    )

    # Where to move "sorted"/"archived" files relative to /storage
    sorted_subdir: str = "Trié"
    archived_subdir: str = "Archivé"
    trash_subdir: str = ".trash"

    @property
    def db_path(self) -> Path:
        return self.config_dir / "db.sqlite3"

    @property
    def thumbnail_dir(self) -> Path:
        return self.config_dir / "thumbnails"

    @property
    def supported_ext_set(self) -> set[str]:
        """Return supported extensions as a set of lowercase strings with dots."""
        return {ext.strip().lower() for ext in self.supported_extensions.split(",") if ext.strip()}

    def keyword_list(self) -> list[str]:
        return [k.strip().lower() for k in self.auto_keywords.split(",") if k.strip()]


settings = Settings()
