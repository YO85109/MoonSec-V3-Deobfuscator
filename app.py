import os
import platform
import random
import string
import subprocess
import uuid

from flask import Flask, render_template, request, jsonify, send_file, session
from dotenv import load_dotenv

load_dotenv()

MOON_EXECUTABLE = os.getenv("MOON_EXECUTABLE")
DECOM_SCRIPT = os.getenv("DECOM_SCRIPT", "decom.lua")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
os.makedirs(WORK_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


def get_lua_path():
    # Explicit override wins (used in the Docker image, where lua5.1 is
    # installed system-wide via apt and just needs to be on PATH).
    env_override = os.getenv("LUA_BIN")
    if env_override:
        return env_override

    system = platform.system()
    if system == "Windows":
        return os.path.join(BASE_DIR, "bin", "lua5.1.exe")
    elif system == "Linux":
        path = os.path.join(BASE_DIR, "bin", "lua5.1")
        if os.path.exists(path):
            os.chmod(path, 0o755)
        return path
    else:
        return "lua5.1"


LUA_BIN = get_lua_path()


def random_name(length=16, extension=""):
    letters = string.ascii_lowercase + string.digits
    name = "".join(random.choice(letters) for _ in range(length))
    return f"{name}{extension}"


def run_pipeline(input_path):
    """
    Mirrors process_pipeline() from the original Discord bot:
      1. Run the MoonSec deobfuscator executable to produce a .luac
      2. Run decom.lua (via bundled lua5.1) to produce the final decompiled .lua
    Returns a dict with keys: ok, decompiled_path, luac_path, error, log
    """
    output_luac_name = random_name(16, ".luac")
    output_luac_path = os.path.join(WORK_DIR, output_luac_name)
    expected_decompiled_path = output_luac_path.replace(".luac", "_decompiled.lua")

    result = {
        "ok": False,
        "decompiled_path": None,
        "luac_path": None,
        "error": None,
        "log": "",
    }

    if not MOON_EXECUTABLE:
        result["error"] = (
            "MOON_EXECUTABLE is not configured on the server. Set it in your .env "
            "to point at the MoonSec deobfuscator executable (see README)."
        )
        return result

    try:
        my_env = os.environ.copy()
        if platform.system() == "Linux":
            my_env["LD_LIBRARY_PATH"] = "/usr/lib:/usr/local/lib"

        cmd_moon = [MOON_EXECUTABLE, "-dev", "-i", input_path, "-o", output_luac_path]
        proc_moon = subprocess.run(
            cmd_moon, capture_output=True, text=True, env=my_env, timeout=120
        )

        if proc_moon.returncode != 0:
            result["error"] = "Moon Error:\n" + (proc_moon.stderr or proc_moon.stdout)
            return result

        cmd_decom = [LUA_BIN, DECOM_SCRIPT, output_luac_path, expected_decompiled_path]
        proc_decom = subprocess.run(
            cmd_decom, capture_output=True, text=True, cwd=BASE_DIR, timeout=120
        )
        result["log"] = proc_decom.stdout or ""

        if os.path.exists(output_luac_path):
            result["luac_path"] = output_luac_path

        if os.path.exists(expected_decompiled_path):
            result["decompiled_path"] = expected_decompiled_path
            result["ok"] = True
        else:
            if not result["error"]:
                result["error"] = "Decompiled file missing. Lua output:\n" + (
                    proc_decom.stdout or proc_decom.stderr or "(no output)"
                )

        return result

    except subprocess.TimeoutExpired:
        result["error"] = "Processing timed out."
        return result
    except Exception as e:
        result["error"] = f"System error: {e}"
        return result


@app.route("/")
def index():
    return render_template("index.html", max_mb=MAX_UPLOAD_MB)


@app.route("/api/deobfuscate", methods=["POST"])
def deobfuscate():
    input_path = None
    luac_path = None
    decompiled_path = None
    try:
        script_text = None

        if "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            if not f.filename.lower().endswith((".lua", ".txt")):
                return jsonify({"ok": False, "error": "Only .lua or .txt files are accepted."}), 400
            input_path = os.path.join(WORK_DIR, random_name(8, ".lua"))
            f.save(input_path)
        else:
            data = request.get_json(silent=True) or {}
            script_text = data.get("script")
            if not script_text or not script_text.strip():
                return jsonify({"ok": False, "error": "No file or script text provided."}), 400
            input_path = os.path.join(WORK_DIR, random_name(8, ".lua"))
            with open(input_path, "w", encoding="utf-8") as fh:
                fh.write(script_text)

        result = run_pipeline(input_path)

        if not result["ok"]:
            return jsonify({"ok": False, "error": result["error"], "log": result["log"]}), 400

        decompiled_path = result["decompiled_path"]
        luac_path = result["luac_path"]

        with open(decompiled_path, "r", encoding="utf-8", errors="replace") as fh:
            decompiled_code = fh.read()

        token = uuid.uuid4().hex
        session[f"dl_{token}"] = decompiled_path
        download_name = os.path.basename(decompiled_path)

        return jsonify(
            {
                "ok": True,
                "code": decompiled_code,
                "download_token": token,
                "download_name": download_name,
            }
        )

    finally:
        # Clean up input + luac immediately (same as the bot did).
        for p in (input_path, luac_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        # NOTE: decompiled_path is intentionally kept until /api/download/<token>
        # is hit (or it can be swept by a periodic cleanup job in production).


@app.route("/api/download/<token>")
def download(token):
    path = session.get(f"dl_{token}")
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "File not found or already downloaded."}), 404
    try:
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    finally:
        try:
            os.remove(path)
        except Exception:
            pass
        session.pop(f"dl_{token}", None)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
