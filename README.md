# MoonSec V3 Lua Deobfuscator — Web App

This is a Flask web version of the original Discord bot. It runs the exact
same two-stage pipeline the bot used:

1. **MOON_EXECUTABLE** (the MoonsecDeobfuscator .NET tool) converts the
   obfuscated `.lua` input into an intermediate `.luac`.
2. **`decom.lua`**, run through the bundled `lua5.1` interpreter, decompiles
   that `.luac` into readable Lua, which is shown in the browser and offered
   as a download.

It is **not** a hosted service — you run it yourself, the same way you'd
have run the bot.

## Easiest deployment: Render (Docker)

This is the recommended path — it builds the .NET deobfuscator for you at
build time, so you don't need .NET, Lua, or any dependency installed on your
own machine or hosting panel.

1. Push this folder to a GitHub repo.
2. Go to [render.com](https://render.com) → **New** → **Web Service**.
3. Connect the repo. Render will detect `render.yaml` automatically (or
   choose **Docker** as the environment manually if asked).
4. Deploy. Render builds the Docker image (this takes a few minutes the
   first time — it's compiling the .NET tool from source) and gives you a
   public URL like `https://moonsec-deobfuscator.onrender.com`.

That's it — no server to SSH into, no dependencies to install by hand.

### Running the same Docker image anywhere else

The same `Dockerfile` works on Railway, Fly.io, a VPS with Docker installed,
or any other Docker-capable host:

```bash
docker build -t moonsec-deobfuscator .
docker run -p 5000:5000 moonsec-deobfuscator
```

Then open `http://localhost:5000` (or the host's public address/port).

## Manual / local (no Docker)

## 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

## 2. Get the MoonSec Deobfuscator executable

This project does not bundle it (same as the original bot — it shelled out
to an external path). Build it from the upstream project:

```bash
git clone https://github.com/tupsutumppu/MoonsecDeobfuscator.git
cd MoonsecDeobfuscator
dotnet build -c Release
```

Note the path to the built executable.

## 3. Configure environment variables

Copy `example.env` to `.env` and fill in:

```env
MOON_EXECUTABLE=/path/to/MoonsecDeobfuscator(.exe)
DECOM_SCRIPT=decom.lua
```

## 4. Run it

```bash
python app.py
```

Then open `http://localhost:5000` in a browser. You can either:

- Paste a script directly into the input box, or
- Drag & drop / browse for a `.lua` or `.txt` file

Click **Deobfuscate**. The decompiled output appears on the right and can be
downloaded or copied.

## Files

- `app.py` — Flask backend (mirrors `process_pipeline()` from `bot.py`)
- `templates/index.html` — single-page UI
- `decom.lua` — unchanged decompiler script from the original bot
- `bin/lua5.1`, `bin/lua5.1.exe`, `bin/lua5.1.dll` — bundled Lua 5.1 interpreter
- `work/` — created at runtime; scripts are processed here and deleted
  immediately after (input + intermediate `.luac`), and the decompiled file
  is deleted right after it's downloaded

## Deploying somewhere public

For anything beyond local use, run this behind a proper WSGI server (e.g.
`gunicorn app:app`) and put it behind HTTPS. Also consider:

- Rate limiting (this shells out to two external processes per request)
- A background cleanup job for `work/` in case a client never downloads
- Restricting `MAX_UPLOAD_MB` and request timeouts to your needs
