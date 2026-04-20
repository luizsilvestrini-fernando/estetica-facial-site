import json
import os
from pathlib import Path
import datetime as dt

post_data = {
    "source_title": "Conheça a Dra. Bruna Silvestrini",
    "source_url": "https://drabrunasilvestrini.com.br/#quem-somos",
    "caption": "A beleza verdadeira é aquela que reflete a sua essência. Aqui na clínica Dra. Bruna Silvestrini, nosso propósito é realçar seus traços com naturalidade, segurança e um cuidado totalmente personalizado. Nossa estrutura foi pensada para proporcionar conforto e excelência em cada detalhe do seu atendimento.\n\n📲 Agende sua avaliação pelo WhatsApp: (11) 99550-5765\nOu clique no link da bio!",
    "hashtags": ["#DraBrunaSilvestrini", "#QuemSomos", "#EsteticaFacial", "#HarmonizacaoFacial", "#Autoestima", "#BelezaNatural", "#ClinicaEsteticaSP", "#Skincare", "#Autocuidado", "#BemEstar"],
    "image_prompt": "Fotografia hiper-realista de uma médica dermatologista sorrindo de jaleco branco, em uma clínica de estética premium muito bem iluminada, tons claros e champagne, 85mm, 4k",
    "alt_text": "Dra. Bruna Silvestrini sorrindo em sua clínica de estética.",
    "posting_suggestion": "Postar no Feed às 18h",
    "story_idea": "Mostre um pouco dos bastidores da clínica e convide as pessoas para uma avaliação.",
    "disclaimer": "Resultados variam. Avaliação individual é indispensável.",
    "is_video": False,
    "video_script": ""
}

out_dir = Path("content/daily-posts")
out_dir.mkdir(parents=True, exist_ok=True)
today = "2026-04-12"
json_path = out_dir / f"{today}.json"

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(post_data, f, ensure_ascii=False, indent=2)

print(f"Gerado {json_path}")