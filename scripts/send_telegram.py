import sys
import json
import os
import urllib.request
import urllib.parse
import ssl
from pathlib import Path

ssl._create_default_https_context = ssl._create_unverified_context

def get_latest_post_json() -> dict:
    # 1. Procura na pasta de backup temporária (onde o arquivo novo sobreviveu ao reset do GitHub Actions)
    d = Path("/tmp/daily-posts")
    if not d.exists():
        # 2. Se não existir no backup, procura no repositório normal
        d = Path("content/daily-posts")
        
    if not d.exists(): return {}
    files = sorted(d.glob("*.json"), reverse=True)
    if not files: return {}
    return json.loads(files[0].read_text(encoding="utf-8"))

def build_image_url(prompt: str) -> str:
    encoded = urllib.parse.quote(prompt or "Daily Post", safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"

def escape_html(text: str) -> str:
    if not text: return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    pr_url = os.environ.get("PR_URL", "")
    
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")
        return

    post = get_latest_post_json()
    if not post:
         # Generic message if json fails
         url = f"https://api.telegram.org/bot{token}/sendMessage"
         data = {"chat_id": chat_id, "text": f"Novo rascunho criado, mas JSON não encontrado! Link: {pr_url}"}
         req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
         try:
             with urllib.request.urlopen(req) as res: print("Telegram enviado (falha JSON).")
         except Exception as e: print(f"Erro: {e}")
         return

    # Preparar conteúdo
    caption_html = escape_html(post.get("caption", ""))
    hashtags = escape_html(" ".join(post.get("hashtags", [])))
    video_script = escape_html(post.get("video_script", ""))
    
    full_msg = f"<b>📝 Novo Rascunho Gerado!</b>\n\n{caption_html}\n\n<i>{hashtags}</i>\n\n"
    
    if post.get("is_video"):
        full_msg += "🎬 <b>Atenção: Este é um roteiro de VÍDEO.</b> A imagem de fundo é enviada acima, mas a música e locução serão geradas apenas quando for pro Instagram.\n"
        full_msg += f"🎙️ <b>Locução:</b> {video_script}\n\n"

    full_msg += f"👉 Para aprovar e postar agora, responda: <b>OK</b>\n"
    full_msg += f"Ou veja o código completo aqui: <a href='{pr_url}'>GitHub PR</a>"

    img_url = post.get("image_url")
    if not img_url:
        img_url = build_image_url(post.get("image_prompt", ""))
    
    # Telegram sendPhoto tem limite de 1024 chars no caption.
    # Se estourar, enviamos a foto com o título e o texto completo numa mensagem separada.
    
    if len(full_msg) < 1000:
        # Envia tudo numa paulada só
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = {
            "chat_id": chat_id,
            "photo": img_url,
            "caption": full_msg,
            "parse_mode": "HTML"
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as res: print("Telegram (Photo + Caption) enviado!")
        except Exception as e: print(f"Erro ao enviar Photo+Caption: {e}")
    else:
        # Envia Foto primeiro com legenda curta
        url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
        data_photo = {
            "chat_id": chat_id,
            "photo": img_url,
            "caption": f"<b>📸 Prévia da Imagem</b>\nAssunto: {escape_html(post.get('source_title', 'Post Diário'))}",
            "parse_mode": "HTML"
        }
        req_photo = urllib.request.Request(url_photo, data=json.dumps(data_photo).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        
        # Envia Texto em seguida (limite 4096)
        url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
        data_msg = {
            "chat_id": chat_id,
            "text": full_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        req_msg = urllib.request.Request(url_msg, data=json.dumps(data_msg).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req_photo) as res: print("Foto enviada.")
            with urllib.request.urlopen(req_msg) as res: print("Texto completo enviado.")
        except Exception as e:
            print(f"Erro no envio duplo: {e}")

if __name__ == "__main__":
    send_telegram()
