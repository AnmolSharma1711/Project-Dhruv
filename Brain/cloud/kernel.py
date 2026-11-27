"""Kaggle notebook source. Package with python -m cloud.notebook build."""
import base64
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

LOCAL = "http://127.0.0.1:11434"
VERSION = "0.40.18"
INSTALLER_HASH = "17659c2456c9e65a3b11056b76da51774911cb822f47bf44f7f3ecc0c40528a8"


def ollama(path, data, timeout):
    req = Request(LOCAL + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        match = re.fullmatch(r"/identity\?challenge=([a-f0-9]{64})", self.path)
        if not match:
            self.send_error(404)
            return
        proof = hmac.new(self.server.auth[7:], match[1].encode(), hashlib.sha256).hexdigest().encode()
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(proof)))
        self.end_headers()
        self.wfile.write(proof)

    def do_POST(self):
        if self.path != "/describe":
            self.send_error(404)
            return
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), self.server.auth):
            self.send_error(401)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512000:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(size))
            image = payload["image"]
            question = payload.get("question", "")
            if not isinstance(question, str) or len(question) > 500:
                raise ValueError("Invalid question")
            jpeg = base64.b64decode(image, validate=True)
            if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                raise ValueError("Expected JPEG")
        except (KeyError, TypeError, ValueError):
            self.send_error(400)
            return
        try:
            result = ollama("/api/generate", {"model": "moondream", "stream": False,
                            "images": [image], "keep_alive": "15m", "options": {"num_predict": 100},
                            "prompt": "Describe visible evidence relevant to this question. "
                                      "Avoid identifying people. Question: " + question}, 20)
            body = json.dumps({"description": result["response"][:1500]}).encode()
        except (KeyError, ValueError, OSError):
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run():
    from kaggle_secrets import UserSecretsClient
    secrets = UserSecretsClient()
    token = secrets.get_secret("VISION_TOKEN").strip()
    domain = secrets.get_secret("NGROK_DOMAIN").strip()
    auth = secrets.get_secret("NGROK_AUTHTOKEN").strip()
    if len(token) < 32 or not auth or not domain or "/" in domain:
        raise ValueError("Configure the notebook secrets and a dedicated ngrok hostname")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyngrok==7.2.12"], check=True)
    from pyngrok import ngrok
    installer = Path("/tmp/dhruv-ollama-install.sh")
    with urlopen(f"https://github.com/ollama/ollama/releases/download/v{VERSION}/install.sh", timeout=30) as response:
        script = response.read()
    if hashlib.sha256(script).hexdigest() != INSTALLER_HASH:
        raise ValueError("Ollama installer checksum mismatch")
    installer.write_bytes(script)
    subprocess.run(["apt-get", "update", "-qq"], check=True)
    subprocess.run(["apt-get", "install", "-y", "zstd"], check=True)
    subprocess.run(["sh", str(installer)], check=True, env=dict(os.environ, OLLAMA_VERSION=VERSION))
    env = dict(os.environ, OLLAMA_HOST="127.0.0.1:11434")
    daemon = subprocess.Popen(["ollama", "serve"], env=env)
    try:
        for _ in range(60):
            try:
                with urlopen(LOCAL + "/api/version", timeout=1):
                    break
            except OSError:
                time.sleep(1)
        subprocess.run(["ollama", "pull", "moondream"], env=env, check=True, timeout=900)
        ollama("/api/generate", {"model": "moondream", "keep_alive": "15m", "stream": False}, 120)
        with HTTPServer(("127.0.0.1", 0), Gateway) as server:
            Gateway.timeout = 10
            server.auth = ("Bearer " + token).encode()
            ngrok.set_auth_token(auth)
            tunnel = ngrok.connect(server.server_port, "http", domain=domain, inspect=False, bind_tls=True)
            if tunnel.public_url.rstrip("/") != "https://" + domain:
                raise RuntimeError("Unexpected public endpoint")
            print("Vision gateway ready on configured hostname", flush=True)
            server.serve_forever()
    finally:
        ngrok.kill()
        daemon.terminate()
        daemon.wait(timeout=10)


if __name__ == "__main__":
    run()
