"""
publish_instagram.py — Publica um post no Instagram via Graph API.

Fluxo:
  1. Lê o JSON mais recente em content/weekly-posts/
  2. Gera (ou reutiliza) uma imagem a partir do image_prompt
  3. Cria um container de mídia na Instagram Graph API
  4. Publica o container no feed

Tokens necessários (env vars ou GitHub Secrets):
  - IG_USER_ID        — ID numérico da conta Instagram Business
  - IG_ACCESS_TOKEN   — Token de longa duração do Facebook Graph API
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import ssl
from pathlib import Path


GRAPH_API = "https://graph.facebook.com/v22.0"


def ssl_context() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


def graph_post(endpoint: str, params: dict, token: str) -> dict:
    """POST to Facebook Graph API and return parsed JSON."""
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode("utf-8")
    url = f"{GRAPH_API}/{endpoint}"
    req = urllib.request.Request(url, data=data, method="POST")
    ctx = ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"Graph API HTTP {e.code}: {body or e.reason}")


def graph_get(endpoint: str, params: dict, token: str) -> dict:
    """GET from Facebook Graph API and return parsed JSON."""
    params["access_token"] = token
    qs = urllib.parse.urlencode(params)
    url = f"{GRAPH_API}/{endpoint}?{qs}"
    req = urllib.request.Request(url)
    ctx = ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"Graph API HTTP {e.code}: {body or e.reason}")


def find_latest_post_json(posts_dir: str = "content/weekly-posts") -> Path:
    """Find the most recent .json post file."""
    d = Path(posts_dir)
    json_files = sorted(d.glob("*.json"), reverse=True)
    if not json_files:
        raise FileNotFoundError(f"Nenhum arquivo .json em {posts_dir}")
    return json_files[0]


def build_image_url(prompt: str) -> str:
    """
    Builds a publicly-accessible image URL from the prompt.
    Uses a placeholder service. In production, replace with your
    preferred image generation API (DALL-E, Midjourney, etc.)
    that returns a public URL.
    """
    # The Instagram API requires a publicly accessible image URL.
    # Option 1: Use the image_prompt to generate via an external API
    # Option 2: If the workflow already generated and uploaded an image,
    #           read the URL from the JSON.
    #
    # For now, we support both: if 'image_url' exists in the JSON, use it.
    # Otherwise, generate from the prompt via a configurable service.
    encoded = urllib.parse.quote(prompt, safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"


def create_media_container(ig_user_id: str, token: str, image_url: str, caption: str) -> str:
    """Create an Instagram media container (step 1 of publishing)."""
    result = graph_post(
        f"{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
        },
        token,
    )
    container_id = result.get("id")
    if not container_id:
        raise RuntimeError(f"Falha ao criar container: {result}")
    return container_id


def wait_for_container(ig_user_id: str, token: str, container_id: str, max_wait: int = 120) -> None:
    """Poll the container status until it's FINISHED or ERROR."""
    for _ in range(max_wait // 5):
        status = graph_get(
            container_id,
            {"fields": "status_code"},
            token,
        )
        code = status.get("status_code", "")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"Container em erro: {status}")
        print(f"  Container status: {code} — aguardando...")
        time.sleep(5)
    raise RuntimeError(f"Timeout esperando container {container_id}")


def publish_container(ig_user_id: str, token: str, container_id: str) -> str:
    """Publish the container (step 2 — the post goes live)."""
    result = graph_post(
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id},
        token,
    )
    media_id = result.get("id")
    if not media_id:
        raise RuntimeError(f"Falha ao publicar: {result}")
    return media_id


def main() -> int:
    ig_user_id = os.environ.get("IG_USER_ID", "").strip()
    ig_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()

    if not ig_user_id or not ig_token:
        print(
            "❌ Variáveis IG_USER_ID e IG_ACCESS_TOKEN são obrigatórias.\n"
            "Configure em GitHub > Settings > Secrets and variables > Actions.",
            file=sys.stderr,
        )
        return 1

    # Pegar o JSON do post mais recente
    post_path = os.environ.get("POST_JSON_PATH", "")
    if post_path:
        post_file = Path(post_path)
    else:
        post_file = find_latest_post_json()

    print(f"📄 Lendo post: {post_file}")
    post_data = json.loads(post_file.read_text(encoding="utf-8"))

    caption = post_data.get("caption", "")
    hashtags = post_data.get("hashtags", [])
    image_prompt = post_data.get("image_prompt", "")
    disclaimer = post_data.get("disclaimer", "")

    # Verificar se já existe uma image_url explícita no JSON
    image_url = post_data.get("image_url", "")
    if not image_url:
        if not image_prompt:
            print("❌ Sem image_url nem image_prompt no JSON.", file=sys.stderr)
            return 1
        print("🎨 Gerando imagem a partir do prompt...")
        image_url = build_image_url(image_prompt)

    # Montar legenda final
    hashtag_str = " ".join(
        [h if h.startswith("#") else f"#{h}" for h in hashtags]
    )
    full_caption = caption.strip()
    if hashtag_str:
        full_caption += "\n\n" + hashtag_str.strip()
    if disclaimer:
        full_caption += "\n\n⚠️ " + disclaimer.strip()

    print(f"📸 Imagem URL: {image_url[:120]}...")
    print(f"📝 Legenda ({len(full_caption)} chars):\n{full_caption[:300]}...")

    # Etapa 1: Criar container
    print("\n⏳ Criando container de mídia no Instagram...")
    container_id = create_media_container(ig_user_id, ig_token, image_url, full_caption)
    print(f"✅ Container criado: {container_id}")

    # Etapa 2: Aguardar processamento
    print("⏳ Aguardando processamento da imagem...")
    wait_for_container(ig_user_id, ig_token, container_id)
    print("✅ Container pronto!")

    # Etapa 3: Publicar
    print("⏳ Publicando no feed...")
    media_id = publish_container(ig_user_id, ig_token, container_id)
    print(f"\n🎉 Post publicado com sucesso!")
    print(f"   Media ID: {media_id}")
    print(f"   Perfil: https://www.instagram.com/dra.brunasilvestrini/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
