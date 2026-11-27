"""Install checksum-verified OpenCV Zoo models into the standalone project."""
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

MODELS = {
    "face_detection_yunet/face_detection_yunet_2023mar.onnx":
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "face_recognition_sface/face_recognition_sface_2021dec.onnx":
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}


def install():
    root = Path(__file__).resolve().parents[1] / "data/models"
    root.mkdir(parents=True, exist_ok=True)
    for rel, digest in MODELS.items():
        target = root / Path(rel).name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        url = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/" + rel
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as tmp:
            path = Path(tmp.name)
        try:
            with urlopen(url, timeout=90) as source, path.open("wb") as out:
                import shutil
                shutil.copyfileobj(source, out)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Face model checksum mismatch")
            path.replace(target)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    install()
