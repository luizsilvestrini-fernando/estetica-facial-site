"""
publish_instagram.py — Publica post ou vídeo no Instagram via instagrapi.
"""

import json
import os
import sys
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def ssl_context() -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    return ctx


def find_latest_post_json(posts_dir: str = "content/daily-posts") -> Path:
    d = Path(posts_dir)
    json_files = sorted(d.glob("*.json"), reverse=True)
    if not json_files:
        raise FileNotFoundError(f"Nenhum arquivo .json em {posts_dir}")
    return json_files[0]


def download_image(url: str, dest: Path) -> Path:
    ctx = ssl_context()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "instagram-poster/1.0", "Accept": "image/*"},
    )
    with urllib.request.urlopen(req, timeout=120, context=ctx) as res:
        data = res.read()
    dest.write_bytes(data)
    return dest


def build_image_url(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt, safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"


def generate_endcard_image(out_path: str):
    """Gera o letreiro final usando PIL sem depender de ImageMagick."""
    from PIL import Image, ImageDraw, ImageFont
    # Fundo rosa claro
    img = Image.new("RGB", (1080, 1080), color=(255, 246, 248))
    draw = ImageDraw.Draw(img)

    # Tenta carregar a logo do repositório
    logo_path = Path("assets/logo_bs_pink_1770921996696.png")
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            # Redimensiona logo
            logo.thumbnail((500, 500))
            x_pos = (1080 - logo.width) // 2
            y_pos = 300
            img.paste(logo, (x_pos, y_pos), mask=logo)
        except Exception as e:
            print(f"Aviso: Falha ao carregar logo: {e}")

    # Fonte fallback
    try:
        font = ImageFont.truetype("arial.ttf", 46)
        font_large = ImageFont.truetype("arial.ttf", 60)
    except IOError:
        font = ImageFont.load_default()
        font_large = font

    text = "Agende sua avaliação GRATUITA pelo WhatsApp!"
    number = "(11) 99550-5765"

    try:
        bb1 = draw.textbbox((0, 0), text, font=font)
        w1 = bb1[2] - bb1[0]
        bb2 = draw.textbbox((0, 0), number, font=font_large)
        w2 = bb2[2] - bb2[0]
    except AttributeError:
        # Fallback para Pillow antigas
        w1, _ = draw.textsize(text, font=font)
        w2, _ = draw.textsize(number, font=font_large)

    draw.text(((1080 - w1) // 2, 800), text, fill=(50, 50, 50), font=font)
    draw.text(((1080 - w2) // 2, 860), number, fill=(210, 50, 100), font=font_large)

    img.save(out_path)


def make_video(image_path: str, transcript: str, out_path: str):
    """Cria o clipe mp4 juntando TTS, imagem e letreiro no final."""
    print("🎬 Iniciando processamento de VÍDEO...")
    try:
        from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    except ImportError:
        raise RuntimeError("Dependências 'moviepy' não instaladas. Rode pip install moviepy.")

    tmp_dir = Path(image_path).parent

    # 1. Gerar TTS
    audio_path = str(tmp_dir / "tts_audio.mp3")
    print(f"🎵 Gerando áudio TTS com texto: '{transcript[:50]}...'")
    
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    
    if elevenlabs_key:
        print("   Usando ElevenLabs TTS (voz ultra-realista)...")
        try:
            # Voice ID "Rachel" (famosa voz feminina em inglês/português fluente)
            voice_id = "21m00Tcm4TlvDq8ikWAM"
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": elevenlabs_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": transcript,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as response:
                with open(audio_path, 'wb') as f:
                    f.write(response.read())
        except Exception as e:
            print(f"   ⚠️ Erro no ElevenLabs TTS: {e}. Tentando OpenAI TTS...")
            elevenlabs_key = None # Força fallback para OpenAI

    if not elevenlabs_key and openai_key:
        print("   Usando OpenAI TTS (voz realista)...")
        try:
            url = "https://api.openai.com/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "tts-1",
                "input": transcript,
                "voice": "nova"
            }
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as response:
                with open(audio_path, 'wb') as f:
                    f.write(response.read())
        except Exception as e:
            print(f"   ⚠️ Erro no OpenAI TTS: {e}. Fazendo fallback para gTTS...")
            openai_key = None

    if not elevenlabs_key and not openai_key:
        print("   ⚠️ Sem chaves de IA (ou erro nelas), usando gTTS (voz robótica)...")
        try:
            from gtts import gTTS
            tts = gTTS(text=transcript, lang='pt', tld='com.br', slow=False)
            tts.save(audio_path)
        except ImportError:
            raise RuntimeError("Dependência 'gTTS' não instalada para o fallback.")

    # 2. Clips principais
    audio_clip = AudioFileClip(audio_path)
    main_img_clip = ImageClip(image_path).set_duration(audio_clip.duration)
    main_img_clip = main_img_clip.set_audio(audio_clip)

    # 3. Clip do letreiro final (Endcard) com silêncio para manter a trilha de áudio
    endcard_path = str(tmp_dir / "endcard.jpg")
    generate_endcard_image(endcard_path)
    
    # Criamos um clip silencioso para o endcard
    from moviepy.audio.AudioClip import AudioArrayClip
    import numpy as np
    silence_duration = 3.5
    # Gerar silêncio (stereo, 44100Hz)
    silence_data = np.zeros((int(44100 * silence_duration), 2))
    silence_audio = AudioArrayClip(silence_data, fps=44100)
    
    endcard_clip = ImageClip(endcard_path).set_duration(silence_duration)
    endcard_clip = endcard_clip.set_audio(silence_audio)

    # 4. Concatenar e renderizar
    final_clip = concatenate_videoclips([main_img_clip, endcard_clip], method="compose")
    print("⏳ Renderizando arquivo MP4...")
    final_clip.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac", temp_audiofile=str(tmp_dir/"temp-audio.m4a"), remove_temp=True)
    
    # 5. Cleanup
    try:
        main_img_clip.close()
        endcard_clip.close()
        audio_clip.close()
        silence_audio.close()
        final_clip.close()
    except:
        pass

    print(f"✅ Vídeo gerado em {out_path}")


def main() -> int:
    ig_username = os.environ.get("IG_USERNAME", "").strip()
    ig_password = os.environ.get("IG_PASSWORD", "").strip()

    if not ig_username or not ig_password:
        print("❌ Variáveis IG_USERNAME e IG_PASSWORD são obrigatórias.", file=sys.stderr)
        return 1

    try:
        from instagrapi import Client
    except ImportError:
        print("❌ Biblioteca 'instagrapi' não encontrada.", file=sys.stderr)
        return 1

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
    is_video = post_data.get("is_video", False)
    video_script = post_data.get("video_script", "")

    if not image_url:
        print("🎨 Gerando imagem de fundo a partir do prompt...")
        image_url = build_image_url(image_prompt)

    hashtag_str = " ".join([h if h.startswith("#") else f"#{h}" for h in hashtags])
    full_caption = caption.strip()
    if hashtag_str:
        full_caption += "\n\n" + hashtag_str.strip()
    if disclaimer:
        full_caption += "\n\n⚠️ " + disclaimer.strip()

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "post_image.jpg"
        print("⬇️ Baixando imagem...")
        try:
            download_image(image_url, img_path)
        except Exception as e:
            print(f"❌ Falha ao baixar imagem: {e}", file=sys.stderr)
            return 1
            
        media_path = img_path
        
        if is_video and video_script.strip():
            vid_path = str(Path(tmpdir) / "post_video.mp4")
            try:
                make_video(str(img_path), video_script, vid_path)
                media_path = Path(vid_path)
            except Exception as e:
                print(f"❌ Falha ao montar vídeo: {e}", file=sys.stderr)
                return 1

        print(f"\n🔐 Fazendo login como @{ig_username}...")
        cl = Client()
        cl.delay_range = [3, 7]
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
            try:
                cl = Client()
                cl.delay_range = [3, 7]
                cl.login(ig_username, ig_password)
                cl.dump_settings(session_file)
            except Exception as login_err:
                print(f"❌ Falha no login do Instagram: {login_err}", file=sys.stderr)
                return 1

        print("\n📤 Publicando no Instagram...")
        time.sleep(5) # Pequeno fôlego para o FS
        try:
            if is_video:
                media = cl.clip_upload(path=media_path, caption=full_caption)
            else:
                media = cl.photo_upload(path=media_path, caption=full_caption)
                
            print(f"\n🎉 Post publicado com sucesso!")
            print(f"   Media ID: {media.pk}")
            ig_url = f"https://www.instagram.com/p/{media.code}/"
            print(f"   URL: {ig_url}")
            
            # Repassar URL pro GitHub Actions
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"ig_url={ig_url}\n")
                    
        except Exception as e:
            print(f"❌ Falha ao publicar: {e}", file=sys.stderr)
            return 1

        print("\n💬 Adicionando comentário com link do WhatsApp...")
        time.sleep(5)
        whatsapp_comment = (
            "✨ Quer saber mais ou fazer uma avaliação?\n"
            "📲 Agende conosco pelo WhatsApp clicando aqui:\n"
            "👉 https://wa.me/5511995505765\n"
        )
        try:
            comment = cl.media_comment(media.pk, whatsapp_comment)
            try:
                cl.comment_pin(media.pk, comment.pk)
            except Exception:
                pass
        except Exception as comment_err:
            print(f"⚠️ Comentário não adicionado: {comment_err}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
