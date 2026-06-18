# SCAFFOLD PHASE 2 : spec PyInstaller pour le sidecar du moteur.
#
#   uv run pyinstaller clipper-engine.spec
#   -> dist/clipper-engine
#   a copier en src-tauri/binaries/clipper-engine-aarch64-apple-darwin
#
# Caveats connus (a traiter en phase 2) :
#   - mediapipe, ctranslate2 (faster-whisper), onnxruntime et av embarquent des
#     binaires natifs et des data files. Utiliser collect_all() pour chacun.
#   - le modele Whisper et blaze_face_short_range.tflite restent telecharges au
#     runtime (cache utilisateur), pas embarques.
#   - ffmpeg/ffprobe : binaires systeme attendus dans le PATH, ou les bundler.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("mediapipe", "ctranslate2", "faster_whisper", "onnxruntime", "av", "scenedetect", "cv2"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["sidecar.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["clipper.api.server"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="clipper-engine",
    console=True,
)
