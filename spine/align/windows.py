"""The fleet's window task: a few consecutive book sentences and a short numbered list of handout sentences.

"The fleet is stupid" (owner): the task is closed. The reader opens no file and answers one line per book
sentence in a fixed grammar; code checks every line and one hidden sentence whose answer is already known
(the probe). A wrong probe rejects the whole window.

    text, key = render(items, res, window, cands, H, label="W1", probe=True)
    verdicts, errors = parse(answer, key, H, items)

`key` maps the window's local numbers back: {"label", "b": {B number: item number}, "h": {H number: handout
position}, "open": [B numbers], "probe": {B number: [H numbers]}}.
"""
import re

from spine import text as T

PROMPT = """You match sentences of a doctor's book to sentences of the college handout.
Do not open any file. Do not use tools. Do not start subagents. Reply with the answer lines only.

{windows}

For every B line that has no [done] mark, write exactly one line, with its window label in front:
<W> B<n> = <H numbers joined by +> <S|R|P>
<W> B<n> = 0
<W> B<n> = X
S = same words. R = same fact, other words. P = the book states only part of it, or more than it.
0 = a teaching sentence, but no H line of that window states it.
X = not teaching content (book title, page number, greeting, picture label).
A heading or a short list item counts as teaching content: match it to the H line that says the same.
Use 1 to 4 H numbers, all from the same window. Two B lines may name the same H.
Example: W1 B3 = H12+H13 R
"""
LINE = re.compile(r"^(W\d+) B(\d+) = (?:(H\d+(?:\+H\d+){0,3}) ([SRP])|(0)|(X))$")
MAX_SPREAD = 3          # H numbers of one answer further apart than this are flagged (a table row may span more)
PROBE_WORDS = 5         # a probe is a full sentence: readers call a bare heading "X", and that is no proof
SAME_OVERLAP = 0.6      # an "S" answer that shares fewer words than this is really an "R"


def render(items, res, window, cands, H, label="W1", probe=True):
    """One window as text, and the key that reads its answers."""
    h_of = {pos: n for n, pos in enumerate(cands, start=1)}
    lines, last = [f"WINDOW {label}", "HANDOUT (lines starting with # are headings, context only)"], None
    for pos in cands:
        ctx = (H.sents[pos].get("ctx") or [None])[0]
        if ctx and ctx != last:
            lines.append(f"# {ctx}")
        last = ctx
        lines.append(f"H{h_of[pos]} {H.sents[pos]['text']}")
    key = {"label": label, "b": {}, "h": {str(n): pos for pos, n in h_of.items()}, "open": [], "probe": {}}
    done = [i for i in window if res[i] and all(p in h_of for p in res[i][1])]
    full = [i for i in done if len(items[i]["text"].split()) >= PROBE_WORDS]
    hidden = full[len(full) // 2] if probe and full else None       # the middle one: its neighbours give no hint
    lines += ["", "BOOK (consecutive sentences, in book order)"]
    for b, i in enumerate(window, start=1):
        key["b"][str(b)] = i
        mark = ""
        if res[i] and i != hidden:
            mark = "[done=" + "+".join(f"H{h_of[p]}" for p in res[i][1] if p in h_of) + "] " if i in done else "[done] "
        else:
            key["open"].append(b)
            if i == hidden:
                key["probe"][str(b)] = [h_of[p] for p in res[i][1]]
        lines.append(f"B{b} {mark}{items[i]['text']}")
    return "\n".join(lines), key


def prompt(rendered):
    return PROMPT.format(windows="\n\n".join(rendered))


def parse(answer, key, H, items):
    """({item number: ("link", [handout positions], rel, flagged) | "0" | "X"}, [errors]) for one window.

    Any error rejects the window: the caller queues it again."""
    got, errors = {}, []
    for raw in answer.splitlines():
        line = " ".join(raw.strip().strip("`").split())
        m = LINE.match(line)
        if not m:
            if line.startswith(key["label"] + " "):
                errors.append(f"not in the grammar: {line[:60]!r}")
            continue
        if m.group(1) != key["label"]:
            continue
        b = int(m.group(2))
        if b not in key["open"]:
            errors.append(f"B{b} is not an open line of {key['label']}")
        elif b in got:
            errors.append(f"B{b} answered twice")
        elif m.group(3):
            hs = [int(h[1:]) for h in m.group(3).split("+")]
            missing = [h for h in hs if str(h) not in key["h"]]
            if missing:
                errors.append(f"B{b}: no H{missing[0]} in {key['label']}")
                continue
            got[b] = ("link", sorted(key["h"][str(h)] for h in hs), m.group(4))
        else:
            got[b] = "0" if m.group(5) else "X"
    errors += [f"B{b} has no answer" for b in key["open"] if b not in got]
    for b, want in key["probe"].items():
        ans = got.get(int(b))
        right = isinstance(ans, tuple) and {key["h"][str(h)] for h in want} & set(ans[1])
        if not right:
            errors.append(f"probe B{b} answered wrong")
    verdicts = {}
    for b, ans in got.items():
        i = key["b"][str(b)]
        if isinstance(ans, tuple):
            _, pos, rel = ans
            share = T.overlap(items[i]["text"], " ".join(H.sents[p]["text"] for p in pos))
            flagged = ((rel == "S" and share < SAME_OVERLAP) or (rel in "RP" and share == 0)
                       or pos[-1] - pos[0] > MAX_SPREAD + len(pos) - 1)
            verdicts[i] = ("link", pos, "R" if rel == "S" and share < SAME_OVERLAP else rel, flagged)
        else:
            verdicts[i] = ans
    return verdicts, errors
