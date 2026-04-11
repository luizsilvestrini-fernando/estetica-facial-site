"""
publish_instagram.py — Publica um post no Instagram via instagrapi.

Fluxo:
  1. Lê o JSON mais recente em content/weekly-posts/
  2. Gera uma imagem a partir do image_prompt (via pollinations.ai)
  3. Faz login no Instagram com username/password
  4. Publica a foto com legenda no feed

Secrets necessários (GitHub Secrets):
  - IG_USERNAME   — Username do Instagram (ex: dra.brunasilvestrini)
  - IG_PASSWORD   — Senha do Instagram
"""

import json
import os
import sys
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def ssl_context() -> ssl.SSLContext:
    """Return SSL context, falling back to unverified for macOS compatibility."""
    ctx = ssl._create_unverified_context()
    return ctx


def find_latest_post_json(posts_dir: str = "content/weekly-posts") -> Path:
    """Find the most recent .json post file."""
    d = Path(posts_dir)
    json_files = sorted(d.glob("*.json"), reverse=True)
    if not json_files:
        raise FileNotFoundError(f"Nenhum arquivo .json em {posts_dir}")
    return json_files[0]


def download_image(url: str, dest: Path) -> Path:
    """Download an image from a URL to a local file."""
    ctx = ssl_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "instagram-poster/1.0",
            "Accept": "image/*",
        },
    )
    with urllib.request.urlopen(req, timeout=120, context=ctx) as res:
        data = res.read()
    dest.write_bytes(data)
    return dest


def build_image_url(prompt: str) -> str:
    """Build a public image URL from the prompt using pollinations.ai."""
    encoded = urllib.parse.quote(prompt, safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"


def main() -> int:
    ig_username = os.environ.get("IG_USERNAME", "").strip()
    ig_password = os.environ.get("IG_PASSWORD", "").strip()

    if not ig_username or not ig_password:
        print(
            "❌ Variáveis IG_USERNAME e IG_PASSWORD são obrigatórias.\n"
            "Configure em GitHub > Settings > Secrets and variables > Actions.",
            file=sys.stderr,
        )
        return 1

    # Importar instagrapi aqui para falhar cedo se não instalado
    try:
        from instagrapi import Client
    except ImportError:
        print("❌ Biblioteca 'instagrapi' não encontrada. Instale com: pip install instagrapi", file=sys.stderr)
        return 1

    # Localizar o JSON do post
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
    image_url = post_data.get("image_url", "")
    disclaimer = post_data.get("disclaimer", "")

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

    print(f"📸 Imagem URL: {image_url[:100]}...")
    print(f"📝 Legenda ({len(full_caption)} chars)")

    # Baixar a imagem
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "post_image.jpg"
        print("⬇️  Baixando imagem...")
        try:
            download_image(image_url, img_path)
        except Exception as e:
            print(f"❌ Falha ao baixar imagem: {e}", file=sys.stderr)
            return 1
        print(f"✅ Imagem salva ({img_path.stat().st_size / 1024:.1f} KB)")

        # Login no Instagram
        print(f"\n🔐 Fazendo login como @{ig_username}...")
        cl = Client()

        # Configurar delays para parecer humano e evitar bloqueios
        cl.delay_range = [3, 7]

        # Tentar carregar sessão salva (evita login repetido)
        session_file = Path("ig_session.json")
        try:
            if session_file.exists():
                cl.load_settings(session_file)
                cl.login(ig_username, ig_password)
                print("✅ Sessão restaurada!")
            else:
                cl.login(ig_username, ig_password)
                print("✅ Login realizado!")
            cl.dump_settings(session_file)
        except Exception as e:
            print(f"⚠️  Erro no login com sessão, tentando login limpo: {e}")
            try:
                cl = Client()
                cl.delay_range = [3, 7]
                cl.login(ig_username, ig_password)
                cl.dump_settings(session_file)
                print("✅ Login realizado (sem sessão prévia)!")
            except Exception as login_err:
                print(f"❌ Falha no login do Instagram: {login_err}", file=sys.stderr)
                print(
                    "\nPossíveis causas:\n"
                    "  - Senha incorreta\n"
                    "  - Autenticação de dois fatores (2FA) ativada\n"
                    "  - Instagram bloqueou login de localização desconhecida\n"
                    "  - Muitas tentativas de login recentes",
                    file=sys.stderr,
                )
                return 1

        # Publicar no feed
        print("\n📤 Publicando no feed do Instagram...")
        try:
            media = cl.photo_upload(
                path=img_path,
                caption=full_caption,
            )
            print(f"\n🎉 Post publicado com sucesso!")
            print(f"   Media ID: {media.pk}")
            print(f"   URL: https://www.instagram.com/p/{media.code}/")
            print(f"   Perfil: https://www.instagram.com/{ig_username}/")
        except Exception as e:
            print(f"❌ Falha ao publicar: {e}", file=sys.stderr)
            return 1

        # Auto-comentário com link clicável do WhatsApp
        import time
        time.sleep(5)  # Esperar post processar

        whatsapp_comment = (
            "✨ Quer saber mais sobre esse procedimento?\n"
            "📲 Agende sua avaliação GRATUITA pelo WhatsApp:\n"
            "👉 https://wa.me/5511995505765\n"
            "\n"
            "Ou mande uma mensagem direta aqui! 💬"
        )

        print("\n💬 Adicionando comentário com link do WhatsApp...")
        try:
            comment = cl.media_comment(media.pk, whatsapp_comment)
            print(f"✅ Comentário adicionado (ID: {comment.pk})")

            # Tentar fixar o comentário no topo
            try:
                cl.comment_pin(media.pk, comment.pk)
                print("📌 Comentário fixado no topo!")
            except Exception as pin_err:
                print(f"⚠️  Não foi possível fixar o comentário (normal em algumas contas): {pin_err}")
        except Exception as comment_err:
            print(f"⚠️  Comentário não adicionado: {comment_err}")
            print("   O post foi publicado com sucesso, mas sem o comentário do WhatsApp.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
