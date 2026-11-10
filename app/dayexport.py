"""Export a lesson day (recap + practice questions) as Markdown or printable HTML."""
from __future__ import annotations

import html

from . import config, library

L = {
    "en": {"recap": "Recap", "taught": "What was taught", "focus": "Focus points: what you should have learned today",
           "vocab": "Key vocabulary", "grammar": "Grammar points", "homework": "Homework or things to review",
           "quiz": "Practice questions", "answer": "Answer", "why": "Why", "unclear": "Note", "print": "Print",
           "ai": "Made by a local AI assistant from an automatic transcript. It can be wrong; the transcript is the source of truth.",
           "options": "Options"},
    "fr": {"recap": "Résumé", "taught": "Ce qui a été enseigné", "focus": "Points clés : ce que vous auriez dû apprendre aujourd'hui",
           "vocab": "Vocabulaire clé", "grammar": "Points de grammaire", "homework": "Devoirs ou à réviser",
           "quiz": "Questions d'entraînement", "answer": "Réponse", "why": "Pourquoi", "unclear": "Note", "print": "Imprimer",
           "ai": "Créé par un assistant IA local à partir d'une transcription automatique. Il peut se tromper ; la transcription fait foi.",
           "options": "Options"},
}


def _blocks(day: str, lang: str, what: str, with_answers: bool):
    s = L.get(lang, L["en"])
    n = library.load_day_notes(day)
    recap, quiz = n.get("recap"), (n.get("quiz") or {}).get("questions")
    out = [("h1", f"{library.day_title(day)} ({day})")]
    if recap and what in ("all", "recap"):
        out.append(("h2", s["recap"]))
        if recap.get("topic"):
            out.append(("p", recap["topic"]))
        for key in ("taught", "focus", "grammar", "homework"):
            if recap.get(key):
                out.append(("h3", s[key]))
                out += [("li", x) for x in recap[key]]
        if recap.get("vocab"):
            out.append(("h3", s["vocab"]))
            for v in recap["vocab"]:
                line = v["arabic"] + (f" ({v['transliteration']})" if v.get("transliteration") else "")
                out.append(("li", f"{line} - {v.get('meaning', '')}"))
        if recap.get("unclear_note"):
            out.append(("p", f"{s['unclear']}: {recap['unclear_note']}"))
    if quiz and what in ("all", "quiz"):
        out.append(("h2", s["quiz"]))
        for i, q in enumerate(quiz, 1):
            out.append(("q", f"{i}. {q['question']}"))
            for j, o in enumerate(q.get("options") or []):
                out.append(("opt", f"{'ABCD'[j]}) {o}"))
            if with_answers:
                out.append(("ans", f"{s['answer']}: {q['answer']}" + (f" ({q['explanation']})" if q.get("explanation") else "")))
    out.append(("note", s["ai"]))
    return out


def export_day(day: str, fmt: str = "md", with_answers: bool = True, what: str = "all") -> str:
    day = library.parse_day(day)
    if fmt not in ("md", "html") or what not in ("all", "recap", "quiz"):
        raise ValueError("unsupported export")
    lang = config.load_settings().get("ui_lang", "en")
    blocks = _blocks(day, lang, what, with_answers)
    if len(blocks) <= 2:
        raise ValueError("Nothing to export yet")
    suffix = "" if what == "all" else f"-{what}"
    suffix += "" if with_answers or what == "recap" else "-no-answers"
    path = library._days_dir() / f"{day}{suffix}.{fmt}"
    if fmt == "md":
        lines = []
        for kind, t in blocks:
            lines.append({"h1": f"# {t}\n", "h2": f"\n## {t}\n", "h3": f"\n### {t}\n", "p": f"{t}\n", "li": f"- {t}",
                          "q": f"\n**{t}**\n", "opt": f"- {t}", "ans": f"  *{t}*", "note": f"\n_{t}_"}[kind])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        tag = {"h1": "h1", "h2": "h2", "h3": "h3", "p": "p", "li": "li", "q": "p class=q", "opt": "p class=o",
               "ans": "p class=a", "note": "p class=n"}
        body, in_ul = [], False
        for kind, t in blocks:
            if in_ul and kind != "li":
                body.append("</ul>")
                in_ul = False
            if kind == "li" and not in_ul:
                body.append("<ul>")
                in_ul = True
            tg = tag[kind]
            body.append(f"<{tg} dir=auto>{html.escape(t)}</{tg.split()[0]}>")
        if in_ul:
            body.append("</ul>")
        page = ("<!doctype html><html><head><meta charset=utf-8><title>%s</title><style>"
                "body{font:16px/1.6 system-ui,Segoe UI,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;color:#222}"
                "h2{margin-top:2em}.q{font-weight:600;margin-top:1.4em}.o{margin:.1em 1.2em}.a{margin:.2em 1.2em;color:#2f6f62}"
                ".n{color:#777;font-size:13px;margin-top:3em}button{margin:0 0 16px}@media print{button{display:none}}"
                "</style></head><body><button onclick=window.print()>%s</button>%s</body></html>"
                % (html.escape(day), html.escape(L.get(lang, L["en"])["print"]), "\n".join(body)))
        path.write_text(page, encoding="utf-8")
    return str(path)
