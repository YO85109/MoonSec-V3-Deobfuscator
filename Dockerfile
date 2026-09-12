# ---------- Stage 1: build the MoonSec deobfuscator from source ----------
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS moonbuild

WORKDIR /src
RUN git clone --depth 1 https://github.com/tupsutumppu/MoonsecDeobfuscator.git .

# Self-contained single-file publish so the runtime image doesn't need
# the .NET runtime installed at all.
RUN dotnet publish -c Release -r linux-x64 \
    -p:PublishSingleFile=true \
    -p:SelfContained=true \
    -p:IncludeNativeLibrariesForSelfExtract=true \
    -o /out

# ---------- Stage 2: runtime image ----------
FROM python:3.11-slim

# lua5.1 for decom.lua; libicu for the .NET self-contained binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    lua5.1 \
    libicu-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py decom.lua ./
COPY templates ./templates

# Built MoonSec deobfuscator from stage 1
COPY --from=moonbuild /out/MoonsecDeobfuscator /app/bin/MoonsecDeobfuscator
RUN chmod +x /app/bin/MoonsecDeobfuscator

ENV MOON_EXECUTABLE=/app/bin/MoonsecDeobfuscator
ENV DECOM_SCRIPT=/app/decom.lua
ENV LUA_BIN=lua5.1
ENV MAX_UPLOAD_MB=5

RUN mkdir -p /app/work

EXPOSE 5000

# Render/most PaaS providers inject $PORT; default to 5000 for local `docker run`.
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} --timeout 120 app:app"]
