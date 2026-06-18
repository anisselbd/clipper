"""Point d'entree du sidecar (phase 2).

Cible PyInstaller : un binaire unique qui lance le moteur FastAPI. Empaquete
par Tauri comme externalBin (clipper-engine-<target-triple>).
"""

from clipper.api.server import main

if __name__ == "__main__":
    main()
