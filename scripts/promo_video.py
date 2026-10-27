"""Vidéo promotionnelle (1080p) générée à partir des vraies captures du projet.

Chaîne : scènes HTML -> PNG 1920x1080 (Edge headless) -> narration française
(voix Windows Hortense, System.Speech) -> clips ffmpeg (zoom lent + fondus)
-> concaténation + fond sonore synthétisé (aucun fichier sous licence).

Usage (Windows) :  python scripts/promo_video.py
Sortie : docs/video/copilote-erp-promo.mp4 (+ affiche docs/video/poster.png)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
OUT = ROOT / "docs" / "video"
WORK = ROOT / "data" / "promo"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
FPS = 30
PAD_S = 0.9  # respiration après chaque phrase

CSS = """
:root { --navy:#0f1830; --ink:#e8ecf7; --muted:#a3aec8; --accent:#9db3f5; --good:#5cc78f; --warn:#e3a948; }
* { box-sizing:border-box; margin:0; }
html,body { width:1920px; height:1080px; overflow:hidden; background:var(--navy); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,sans-serif; }
.stage { width:1920px; height:1080px; padding:110px 140px; display:grid; align-content:center; gap:34px;
  background: radial-gradient(1200px 700px at 85% 15%, #1d2c5a 0%, transparent 60%), var(--navy); }
.eyebrow { font:500 26px "IBM Plex Mono",monospace; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
h1 { font:700 104px/1.02 "IBM Plex Sans Condensed",sans-serif; letter-spacing:-.015em; max-width:1500px; }
h1 em { font-style:normal; color:var(--accent); }
h2 { font:600 72px/1.08 "IBM Plex Sans Condensed",sans-serif; max-width:1500px; }
p.sub { font-size:38px; line-height:1.45; color:var(--muted); max-width:1450px; }
ul { list-style:none; padding:0; display:grid; gap:26px; }
li { font-size:44px; line-height:1.3; padding-left:56px; position:relative; }
li::before { content:""; position:absolute; left:0; top:22px; width:28px; height:4px; background:var(--accent); }
.kpis { display:grid; grid-template-columns:repeat(5,1fr); gap:2px; background:rgba(255,255,255,.14); border-radius:10px; overflow:hidden; }
.kpi { background:var(--navy); padding:40px 30px; display:grid; gap:10px; }
.kpi b { font:700 92px "IBM Plex Sans Condensed",sans-serif; color:#fff; }
.kpi span { font-size:28px; color:var(--muted); line-height:1.3; }
.shotstage { width:1920px; height:1080px; display:grid; grid-template-rows:1fr auto; background:var(--navy); }
.frame { display:grid; place-items:center; padding:48px 60px 26px; overflow:hidden; }
.frame img { max-width:100%; max-height:860px; border-radius:12px; box-shadow:0 30px 80px rgba(0,0,0,.5); border:1px solid rgba(255,255,255,.14); }
.frame.light img { background:#fff; padding:14px; }
.band { padding:26px 60px 40px; display:flex; gap:30px; align-items:baseline; }
.band .tag { font:500 24px "IBM Plex Mono",monospace; color:var(--accent); letter-spacing:.12em; text-transform:uppercase; white-space:nowrap; }
.band .cap { font:500 40px/1.3 "IBM Plex Sans",sans-serif; }
.chips { display:flex; flex-wrap:wrap; gap:16px; }
.chip { font:500 30px "IBM Plex Mono",monospace; border:1px solid rgba(255,255,255,.3); border-radius:6px; padding:10px 18px; }
.url { font:500 40px "IBM Plex Mono",monospace; color:var(--accent); }
"""
FONTS = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:'
    'wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap">'
)


def page(body: str) -> str:
    return f'<!doctype html><html lang="fr"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{body}</body></html>'


def card(eyebrow: str, title: str, sub: str = "", extra: str = "") -> str:
    sub_html = f'<p class="sub">{sub}</p>' if sub else ""
    return page(f'<div class="stage"><span class="eyebrow">{eyebrow}</span><h1>{title}</h1>{sub_html}{extra}</div>')


def shot(image: str, tag: str, caption: str, light: bool = False) -> str:
    src = (IMG / image).as_uri()
    cls = "frame light" if light else "frame"
    return page(
        f'<div class="shotstage"><div class="{cls}"><img src="{src}"></div>'
        f'<div class="band"><span class="tag">{escape(tag)}</span><span class="cap">{caption}</span></div></div>'
    )


KPIS = (
    '<div class="kpis">'
    + "".join(
        f'<div class="kpi"><b>{v}</b><span>{t}</span></div>'
        for v, t in [
            ("5/5", "fidélité aux sources, notée par 2 LLM juges"),
            ("3/3", "refus corrects : hors sujet et injection"),
            ("2,0 s", "latence médiane sur GPU local"),
            ("0 €", "par requête, données sur le poste"),
            ("76", "tests verts sur un vrai SQL Server"),
        ]
    )
    + "</div>"
)

# (identifiant, html, narration, zoom final)
SCENES = [
    ("01-titre", card("Copilote IA pour ERP Sage &amp; EBP", "Un copilote qui <em>cite ses sources</em> et refuse d'inventer."),
     "Dans un ERP, une réponse plausible mais fausse coûte cher. Voici un copilote qui cite ses sources, et qui refuse d'inventer.", 1.04),
    ("02-probleme", card("Le besoin", "Les questions d'une direction financière",
        extra="<ul><li>« Un client a 70 jours de retard : garde-t-il sa remise ? »</li>"
              "<li>« Quelles factures dépassent 60 jours de retard ? »</li>"
              "<li>« Quelles sont les étapes de la clôture mensuelle ? »</li></ul>"),
     "Un directeur financier pose ses questions en français : remises, retards de paiement, clôture mensuelle. "
     "La réponse est à moitié dans les procédures, à moitié dans les données de gestion.", 1.03),
    ("03-demo", shot("demo-retards.png", "Démo réelle", "Chaque ligne cite sa source. Les jours de retard sont calculés par le code."),
     "Le copilote cherche dans les documents, interroge l'ERP en lecture seule, et cite chaque affirmation. "
     "Les jours de retard sont calculés par le code, jamais par le modèle.", 1.10),
    ("04-refus", shot("demo-refus.png", "Garde-fou", "Tentative d'injection : refus en 0,8 seconde."),
     "Une question hors sujet, ou une tentative de manipulation ? Il refuse, en moins d'une seconde.", 1.06),
    ("05-archi", shot("architecture-1.png", "Architecture", "Un seul code : CI, GPU local avec Ollama, ou cloud Azure.", light=True),
     "Un seul code, trois environnements : l'intégration continue, un poste équipé d'un GPU avec Ollama, ou le cloud Azure. "
     "Pour changer de modèle, on change une variable.", 1.12),
    ("06-gpu", card("100 % local", "Un vrai LLM sur une carte graphique de bureau.",
        "Aucune donnée ne quitte le poste de l'entreprise.",
        '<div class="chips"><span class="chip">RTX 4070 Ti SUPER · 16 Go</span><span class="chip">Ollama</span>'
        '<span class="chip">gemma4:e4b</span><span class="chip">bge-m3</span><span class="chip">LangChain</span></div>'),
     "Ici, tout tourne sur une carte graphique de bureau, avec des modèles ouverts. Aucune donnée ne quitte le poste.", 1.03),
    ("07-llmops", shot("demo-llmops.png", "LLMOps", "Mesurer, détecter, corriger, vérifier."),
     "Chaque version est mesurée : fidélité notée par deux modèles juges, latence, coût. "
     "Le banc a détecté une hallucination ; sa cause a été corrigée, et la fidélité est remontée à cinq sur cinq.", 1.14),
    ("08-chiffres", card("Résultats mesurés", "Les chiffres, pas les promesses.", extra=KPIS),
     "Cinq sur cinq en fidélité. Tous les refus corrects. Deux secondes de réponse. "
     "Et soixante-seize tests verts sur un vrai SQL Server.", 1.03),
    ("09-k8s", shot("architecture-7.png", "Production", "Image Docker testée · manifestes Kubernetes GPU et cloud.", light=True),
     "Prêt pour la production : une image Docker testée de bout en bout, et des manifestes Kubernetes pour un cluster GPU ou pour le cloud.", 1.12),
    ("10-fin", card("Copilote ERP sourcé", "Le code, la démarche et les mesures sont publics.",
        extra='<p class="url">github.com/PDUCLOS/LLMRAGlangchain</p><p class="sub">Patrice Duclos · IA &amp; automatisation ERP</p>'),
     "Copilote ERP. Le code, la démarche et les mesures sont sur GitHub.", 1.04),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def render_png(html: str, png: Path) -> None:
    src = png.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
         f"--user-data-dir={WORK / 'edge-profile'}", "--window-size=1920,1080",
         "--virtual-time-budget=4000", f"--screenshot={png}", src.as_uri()])


def narrate(text: str, wav: Path) -> None:
    txt = wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.SelectVoice('Microsoft Hortense Desktop'); $s.Rate = 0;"
        f"$s.SetOutputToWaveFile('{wav}');"
        f"$s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8)); $s.Dispose()"
    )
    run(["powershell", "-NoProfile", "-Command", ps])


def duration(path: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def encoder() -> list[str]:
    probe = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_nvenc" in probe:
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]


def clip(png: Path, wav: Path, zoom: float, mp4: Path) -> float:
    dur = duration(wav) + PAD_S
    frames = int(dur * FPS)
    step = (zoom - 1.0) / frames
    vf = (
        f"[0:v]scale=3840:2160,zoompan=z='min(1+{step:.6f}*on,{zoom})':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps={FPS},"
        f"fade=t=in:st=0:d=0.45,fade=t=out:st={dur - 0.45:.2f}:d=0.45,format=yuv420p[v];"
        f"[1:a]adelay=350|350,apad,atrim=0:{dur:.2f},aformat=sample_rates=48000:channel_layouts=stereo[a]"
    )
    run([FFMPEG, "-y", "-loop", "1", "-i", str(png), "-i", str(wav), "-filter_complex", vf,
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", *encoder(), "-c:a", "aac", "-b:a", "192k", str(mp4)])
    return dur


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    clips, total = [], 0.0
    for name, html, text, zoom in SCENES:
        png, wav, mp4 = WORK / f"{name}.png", WORK / f"{name}.wav", WORK / f"{name}.mp4"
        render_png(html, png)
        narrate(text, wav)
        total += clip(png, wav, zoom, mp4)
        clips.append(mp4)
        print(f"  {name}: {total:5.1f} s")

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    joined = WORK / "joined.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])

    # Nappe sonore synthétisée (accord de quinte, battement lent) mixée sous la voix.
    pad = (
        f"aevalsrc='0.05*sin(2*PI*110*t)*(0.6+0.4*sin(2*PI*0.08*t))+0.035*sin(2*PI*164.81*t)"
        f"+0.03*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*0.05*t+1))+0.02*sin(2*PI*329.63*t)':"
        f"s=48000:d={total:.2f},afade=t=in:d=2,afade=t=out:st={total - 3:.2f}:d=3,"
        f"lowpass=f=900,aformat=channel_layouts=stereo,volume=0.55[pad]"
    )
    final = OUT / "copilote-erp-promo.mp4"
    run([FFMPEG, "-y", "-i", str(joined), "-filter_complex",
         f"{pad};[0:a][pad]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,loudnorm=I=-16:TP=-1.5[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(final)])
    shutil.copy(WORK / "01-titre.png", OUT / "poster.png")
    print(f"Vidéo : {final} ({total:.1f} s, {final.stat().st_size / 1e6:.1f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
