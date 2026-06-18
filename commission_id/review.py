"""Interactive review tool: pop up each unidentified image, let you name the
artist, then propagate that label to exact-duplicate files (automatic) and to
visual look-alikes (with your confirmation)."""
from __future__ import annotations
import argparse
import sys

from .config import Config
from .pipeline import identify_all
from .decisions import Decisions
from .cache import Cache
from . import similarity

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # no Tk available (e.g. headless) — module still imports
    tk = None
    ttk = None


# ---- testable helpers (no GUI) -------------------------------------------

def build_guesses(ident, limit=5):
    """Distinct artist guesses for an image, best-first, for quick-pick buttons."""
    best = {}
    for c in ident.candidates:
        name = (c.canonical or c.name).strip()
        if not name:
            continue
        key = name.lower()
        if key not in best or c.weight > best[key][1]:
            best[key] = (name, c.weight, c.source)
    ranked = sorted(best.values(), key=lambda x: x[1], reverse=True)
    return ranked[:limit]


def in_scope(ident, scope):
    if scope == "all":
        return True
    if scope == "review":
        return ident.status == "review"
    if scope == "unknown":
        return ident.status == "unknown"
    return ident.status in ("review", "unknown")  # "both" (default)


# ---- GUI ------------------------------------------------------------------

def _run_gui(idents, cfg, decisions, cache, scope, style_threshold,
             dup_threshold, max_style):
    from PIL import Image, ImageTk

    items = [it.item for it in idents]
    phash_of = {it.rel_path: it.phash for it in items}
    # descriptors for every image (cached by phash)
    vec_of = {}
    print("Preparing visual fingerprints ...", file=sys.stderr)
    for it in items:
        v = cache.get_descriptor(it.phash) if it.phash else None
        if v is None:
            v = similarity.visual_descriptor(it.path)
            if v is not None and it.phash:
                cache.put_descriptor(it.phash, v)
        vec_of[it.rel_path] = v

    pool_phash = [(it.rel_path, it.phash) for it in items]
    pool_vecs = [(it.rel_path, vec_of[it.rel_path]) for it in items]
    item_by_key = {it.rel_path: it for it in items}

    def decided(phash):
        return bool(decisions.get(phash)) if phash else False

    worklist = [it for it in idents if in_scope(it, scope)]

    root = tk.Tk()
    root.title("Commission artist review")
    state = {"i": 0, "thumbs": []}

    top = ttk.Frame(root, padding=8)
    top.pack(fill="both", expand=True)
    img_label = ttk.Label(top)
    img_label.pack()
    caption = ttk.Label(top, font=("TkDefaultFont", 10, "bold"))
    caption.pack(pady=(6, 0))
    guess_frame = ttk.Frame(top)
    guess_frame.pack(pady=6)
    entry_frame = ttk.Frame(top)
    entry_frame.pack(pady=4)
    ttk.Label(entry_frame, text="Artist:").pack(side="left")
    entry = ttk.Entry(entry_frame, width=30)
    entry.pack(side="left", padx=4)
    nav = ttk.Frame(top)
    nav.pack(pady=6)

    def next_pending(start):
        i = start
        while i < len(worklist):
            if not decided(worklist[i].item.phash):
                return i
            i += 1
        return len(worklist)

    def show():
        idx = next_pending(state["i"])
        state["i"] = idx
        for w in guess_frame.winfo_children():
            w.destroy()
        entry.delete(0, "end")
        if idx >= len(worklist):
            caption.config(text="All done — close this window, then re-run with --apply.")
            img_label.config(image="")
            return
        ident = worklist[idx]
        it = ident.item
        try:
            im = Image.open(it.path).convert("RGB")
            im.thumbnail((680, 680))
            ph = ImageTk.PhotoImage(im)
        except Exception:
            ph = None
        img_label.image = ph
        img_label.config(image=ph if ph else "")
        remaining = sum(1 for w in worklist if not decided(w.item.phash))
        caption.config(text=f"{it.rel_path}    [{ident.status}]    ({remaining} left)")
        for n, (name, weight, source) in enumerate(build_guesses(ident), 1):
            b = ttk.Button(guess_frame, text=f"{n}. {name}  ({source} {weight:.2f})",
                           command=lambda nm=name: confirm(nm))
            b.pack(side="top", anchor="w")
        entry.focus_set()

    def confirm(name):
        name = (name or "").strip()
        if not name:
            return
        ident = worklist[state["i"]]
        cur = ident.item
        ph = cur.phash
        decisions.set(ph, name, "human", avg=cur.avg_rgb)
        # exact-duplicate propagation (automatic, colour-guarded)
        for it2 in items:
            if it2.rel_path == cur.rel_path:
                continue
            if (it2.phash and not decided(it2.phash)
                    and similarity.is_near_dup(ph, it2.phash, dup_threshold)
                    and similarity.color_close(cur.avg_rgb, it2.avg_rgb)):
                decisions.set(it2.phash, name, "propagated-dup", avg=it2.avg_rgb,
                              note=f"duplicate of {cur.filename}")
        # style propagation (ask)
        tvec = vec_of.get(ident.item.rel_path)
        neighbors = []
        if tvec is not None:
            pool = [(k, v) for k, v in pool_vecs
                    if k != cur.rel_path and not decided(phash_of.get(k))
                    and not (phash_of.get(k) and similarity.is_near_dup(ph, phash_of[k], dup_threshold)
                             and similarity.color_close(cur.avg_rgb, item_by_key[k].avg_rgb))]
            neighbors = similarity.style_neighbors(tvec, pool, style_threshold)[:max_style]
        if neighbors:
            ask_style(name, neighbors)
        else:
            state["i"] += 1
            show()

    def ask_style(name, neighbors):
        win = tk.Toplevel(root)
        win.title(f"Look-alikes for '{name}' — confirm")
        ttk.Label(win, padding=6,
                  text=f"These look stylistically similar. Tick the ones also by '{name}':").pack()
        canvas = tk.Canvas(win, width=760, height=460)
        sb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        grid = ttk.Frame(canvas)
        grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=grid, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        thumbs = []
        vars_ = []
        from PIL import Image, ImageTk
        for col, (key, sim) in enumerate(neighbors):
            r, c = divmod(col, 4)
            cell = ttk.Frame(grid, padding=4)
            cell.grid(row=r, column=c, sticky="n")
            it = item_by_key[key]
            try:
                im = Image.open(it.path).convert("RGB")
                im.thumbnail((150, 150))
                tph = ImageTk.PhotoImage(im)
            except Exception:
                tph = None
            thumbs.append(tph)
            lbl = ttk.Label(cell, image=tph if tph else None)
            lbl.image = tph
            lbl.pack()
            var = tk.IntVar(value=1)
            vars_.append((var, it))
            ttk.Checkbutton(cell, text=f"{int(sim*100)}%  {it.filename[:18]}", variable=var).pack()
        state["thumbs"] = thumbs  # keep refs alive

        def apply_style():
            for var, it2 in vars_:
                if var.get() and it2.phash and not decided(it2.phash):
                    decisions.set(it2.phash, name, "propagated-style", avg=it2.avg_rgb,
                                  note="style match (you confirmed)")
            win.destroy()
            state["i"] += 1
            show()

        def skip_style():
            win.destroy()
            state["i"] += 1
            show()

        btns = ttk.Frame(win, padding=6)
        btns.pack()
        ttk.Button(btns, text="Apply to ticked", command=apply_style).pack(side="left", padx=4)
        ttk.Button(btns, text="None of these", command=skip_style).pack(side="left", padx=4)

    def skip():
        state["i"] += 1
        show()

    def back():
        state["i"] = max(0, state["i"] - 1)
        show()

    ttk.Button(nav, text="Use typed name", command=lambda: confirm(entry.get())).pack(side="left", padx=3)
    ttk.Button(nav, text="Skip / Unknown", command=skip).pack(side="left", padx=3)
    ttk.Button(nav, text="Back", command=back).pack(side="left", padx=3)
    ttk.Button(nav, text="Quit & save", command=root.destroy).pack(side="left", padx=3)
    root.bind("<Return>", lambda e: confirm(entry.get()))
    for d in range(1, 10):
        def pick(e, dd=d):
            gs = build_guesses(worklist[state["i"]]) if state["i"] < len(worklist) else []
            if dd <= len(gs):
                confirm(gs[dd - 1][0])
        root.bind(str(d), pick)
    show()
    root.mainloop()


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="commission-id-review",
        description="Pop up unidentified images and label the artist, with dup + style propagation.")
    p.add_argument("folder")
    p.add_argument("-c", "--config", default="config.yaml")
    p.add_argument("--cache", default="cache/cache.sqlite")
    p.add_argument("--decisions", default="decisions.sqlite")
    p.add_argument("--scope", choices=["both", "review", "unknown", "all"], default="both",
                   help="Which images to review (default: review + unknown).")
    p.add_argument("--live", action="store_true",
                   help="Allow live API lookups during review (default: cached results only).")
    p.add_argument("--style-threshold", type=float, default=0.92,
                   help="Cosine similarity to count as a style look-alike (0-1).")
    p.add_argument("--dup-threshold", type=int, default=6,
                   help="Max perceptual-hash distance to count as the same artwork (0-64).")
    p.add_argument("--max-style", type=int, default=24, help="Max look-alikes to show at once.")
    args = p.parse_args(argv)

    if tk is None:
        print("Tkinter is not available in this Python. On Windows/macOS the python.org "
              "build includes it; on Linux install python3-tk.", file=sys.stderr)
        return 2

    cfg = Config.load(args.config)
    print("Identifying (cached; run the plain dry-run first if this is slow) ...", file=sys.stderr)
    idents = identify_all(args.folder, cfg, cache_path=args.cache,
                          decisions_path=args.decisions, live=args.live)
    decisions = Decisions(args.decisions)
    cache = Cache(args.cache)
    try:
        _run_gui(idents, cfg, decisions, cache, args.scope,
                 args.style_threshold, args.dup_threshold, args.max_style)
    finally:
        print(f"\nSaved {decisions.count()} labels to {args.decisions}.")
        print("Re-run the main tool with --apply to sort using your labels.")
        decisions.close()
        cache.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
