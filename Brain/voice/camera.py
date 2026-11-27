"""One on-demand camera worker. Killing it releases V4L2 even if the driver stalls."""
import asyncio
import base64
import json
import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit


class Camera:
    def __init__(self, client):
        self.client = client
        self.child = None
        self.lock = asyncio.Lock()
        self.url = os.getenv("VISION_URL", "").rstrip("/")
        self.token = os.getenv("VISION_TOKEN", "")
        if self.url:
            url = urlsplit(self.url)
            if (url.scheme != "https" or not url.hostname or url.path or url.username
                    or url.password or url.query or url.fragment or len(self.token) < 32):
                raise ValueError("VISION_URL requires an HTTPS origin and a strong VISION_TOKEN")

    async def close(self):
        if self.child:
            if self.child.returncode is None:
                try:
                    self.child.kill()
                except ProcessLookupError:
                    pass
            await self.child.communicate()
            self.child = None

    async def sample(self, kind):
        async with self.lock:
            try:
                async with asyncio.timeout(12):
                    if not self.child:
                        self.child = await asyncio.create_subprocess_exec(
                            sys.executable, "-m", "voice.camera", stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE, limit=2**20)
                    self.child.stdin.write((kind + "\n").encode())
                    await self.child.stdin.drain()
                    return json.loads(await self.child.stdout.readline())
            except BaseException:
                await self.close()
                raise

    async def observe(self, kind, question=""):
        if kind == "scene" and not self.url:
            return {"unavailable": "Visual description service is offline."}
        if kind == "scene":
            nonce = secrets.token_hex(32)
            proof = await self.client.get(self.url + "/identity", params={"challenge": nonce},
                                          headers={"ngrok-skip-browser-warning": "1"}, timeout=4)
            proof.raise_for_status()
            expected = hmac.new(self.token.encode(), nonce.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(proof.content, expected.encode()):
                raise ValueError("Vision gateway identity mismatch")
        sample = await self.sample(kind)
        if kind != "scene" or "image" not in sample:
            return sample
        async with asyncio.timeout(15):
            response = await self.client.post(self.url + "/describe",
                headers={"Authorization": "Bearer " + self.token, "ngrok-skip-browser-warning": "1"},
                json={"image": sample["image"], "question": question[:500]})
            response.raise_for_status()
            caption = response.json()["description"]
            return {"current_scene": str(caption)[:1500]}


class FaceGallery:
    def __init__(self, cv, data):
        self.cv = cv
        self.people = json.loads((data / "people.json").read_text(encoding="utf8"))
        self.gallery = []
        if not self.people:
            return
        models = data / "models"
        self.detect = cv.FaceDetectorYN.create(str(models / "face_detection_yunet_2023mar.onnx"),
                                               "", (320, 320), 0.9)
        self.recognize = cv.FaceRecognizerSF.create(str(models / "face_recognition_sface_2021dec.onnx"), "")
        for key, profile in self.people.items():
            filename = profile["image"]
            if Path(filename).name != filename:
                raise ValueError("Face image must be a filename")
            frame = cv.imread(str(data / "faces" / filename))
            if frame is None:
                raise ValueError("Missing enrollment image")
            features = self.features(frame)
            if len(features) != 1:
                raise ValueError("Each enrollment image must show one clear face")
            self.gallery.append((key, features[0]))

    def features(self, frame):
        h, w = frame.shape[:2]
        if max(h, w) > 640:
            scale = 640 / max(h, w)
            frame = self.cv.resize(frame, (round(w*scale), round(h*scale)))
        self.detect.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = self.detect.detect(frame)
        if faces is None or len(faces) != 1:
            return []
        crop = self.recognize.alignCrop(frame, faces[0])
        return [self.recognize.feature(crop).copy()]

    def identify(self, frame):
        if self.gallery:
            for face in self.features(frame):
                scores = sorted(((self.recognize.match(face, other, self.cv.FaceRecognizerSF_FR_COSINE), key)
                                 for key, other in self.gallery), reverse=True)
                score, key = scores[0]
                if score >= 0.50 and (len(scores) == 1 or score - scores[1][0] >= 0.08):
                    profile = self.people[key]
                    return {"visitor": profile["name"], "context": profile["context"]}
        return {"visitor": "unknown"}


def worker():
    import cv2 as cv
    cv.setNumThreads(1)
    gallery = None
    for line in sys.stdin:
        try:
            device = os.getenv("CAMERA_DEVICE", "/dev/video0")
            cap = cv.VideoCapture(device, cv.CAP_V4L2)
            try:
                cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera unavailable")
            finally:
                cap.release()
            if line.strip() == "face":
                if gallery is None:
                    gallery = FaceGallery(cv, Path(os.getenv("GUIDE_DATA", "/app/data")))
                result = gallery.identify(frame)
            else:
                ok, image = cv.imencode(".jpg", frame, [cv.IMWRITE_JPEG_QUALITY, 75])
                if not ok:
                    raise RuntimeError("Frame encoding failed")
                result = {"image": base64.b64encode(image).decode()}
        except Exception as exc:
            print("Camera operation failed:", type(exc).__name__, file=sys.stderr, flush=True)
            result = {"unavailable": "No usable visual observation."}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    worker()
