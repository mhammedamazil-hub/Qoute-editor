"""Byte-level BPE tokenizer with a corpus-derived vocabulary.

Hugging Face is unreachable from the target environment, so the brain cannot
pull a pretrained SentencePiece/BPE model.  Instead we derive a compact BPE
vocabulary from the local corpus and train every downstream model from scratch.

Design notes
------------
* One consistent id space everywhere: ``0..3`` specials, ``4..259`` raw bytes,
  ``260..`` learned merges.  (``len(SPECIAL_TOKENS) + 256 + rank``.)
* Merges are learned greedily by pair frequency (classic BPE), which keeps the
  tokenizer tiny yet able to represent identifiers and punctuation compactly.
* Encoding is exact: ``decode(encode(text)) == text`` for any UTF-8 input.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

SPECIAL_TOKENS = ("<pad>", "<bos>", "<eos>", "<unk>")
N_SPECIAL = len(SPECIAL_TOKENS)
BYTE_OFFSET = N_SPECIAL
MERGE_OFFSET = N_SPECIAL + 256
_SPLIT = re.compile(r"\S+|\s")


class Tokenizer:
    PAD = 0
    BOS = 1
    EOS = 2
    UNK = 3

    def __init__(self, merges: list[tuple[int, int]], vocab_size: int = 4096) -> None:
        self.merges = merges
        self.vocab_size = vocab_size
        self._ranks: dict[tuple[int, int], int] = {p: i for i, p in enumerate(merges)}
        # Byte expansion cache for decoding fast.
        self._expand_cache: dict[int, bytes] = {}

    def __len__(self) -> int:
        return max(self.vocab_size, MERGE_OFFSET + len(self.merges))

    # ------------------------------------------------------------------ io
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"vocab_size": self.vocab_size, "merges": [list(m) for m in self.merges]}
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "Tokenizer":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            merges=[(int(a), int(b)) for a, b in data["merges"]],
            vocab_size=int(data.get("vocab_size", 4096)),
        )

    # ------------------------------------------------------------- training
    @classmethod
    def train(cls, texts: list[str], vocab_size: int = 4096, verbose: bool = False) -> "Tokenizer":
        """Learn BPE merges from ``texts``.

        Works over word/whitespace chunks so merges never cross word boundaries,
        which keeps English words and code identifiers atomic.
        """
        seqs: list[list[int]] = [
            [BYTE_OFFSET + b for b in word.encode("utf-8")] for t in texts for word in _SPLIT.findall(t)
        ]
        seqs = [s for s in seqs if s]
        merges: list[tuple[int, int]] = []
        budget = max(0, vocab_size - MERGE_OFFSET)

        # Index pair -> count incrementally for speed (recount per round is O(n*k)).
        while len(merges) < budget:
            counts: Counter[tuple[int, int]] = Counter()
            for s in seqs:
                counts.update(zip(s, s[1:]))
            if not counts:
                break
            pair, freq = counts.most_common(1)[0]
            if freq < 2:
                break
            new_id = MERGE_OFFSET + len(merges)
            merges.append(pair)
            a, b = pair
            updated: list[list[int]] = []
            for s in seqs:
                if len(s) < 2:
                    updated.append(s)
                    continue
                out: list[int] = []
                i = 0
                while i < len(s):
                    if i < len(s) - 1 and s[i] == a and s[i + 1] == b:
                        out.append(new_id)
                        i += 2
                    else:
                        out.append(s[i])
                        i += 1
                updated.append(out)
            seqs = updated
            if verbose and len(merges) % 200 == 0:
                print(f"  bpe merges: {len(merges)}/{budget}")
        return cls(merges=merges, vocab_size=vocab_size)

    # ------------------------------------------------------------- encoding
    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> list[int]:
        ids: list[int] = [self.BOS] if add_bos else []
        ranks = self._ranks
        for word in _SPLIT.findall(text):
            seq = [BYTE_OFFSET + b for b in word.encode("utf-8")]
            while len(seq) > 1:
                best_rank: int | None = None
                best_pos = -1
                for i in range(len(seq) - 1):
                    r = ranks.get((seq[i], seq[i + 1]))
                    if r is not None and (best_rank is None or r < best_rank):
                        best_rank, best_pos = r, i
                if best_rank is None:
                    break
                seq[best_pos : best_pos + 2] = [MERGE_OFFSET + best_rank]
            ids.extend(seq)
        if add_eos:
            ids.append(self.EOS)
        return ids

    def decode(self, ids: list[int]) -> str:
        pieces: list[bytes] = []
        for i in ids:
            if i in (self.PAD, self.BOS):
                continue
            if i == self.EOS:
                break
            if i == self.UNK:
                pieces.append(b"?")
            else:
                pieces.append(self.expand(i))
        return b"".join(pieces).decode("utf-8", errors="replace")

    def expand(self, token: int) -> bytes:
        cached = self._expand_cache.get(token)
        if cached is not None:
            return cached
        if token < MERGE_OFFSET:
            return bytes([token - BYTE_OFFSET]) if token >= BYTE_OFFSET else b"?"
        idx = token - MERGE_OFFSET
        if 0 <= idx < len(self.merges):
            a, b = self.merges[idx]
            out = self.expand(a) + self.expand(b)
            self._expand_cache[token] = out
            return out
        return b"?"

    # ------------------------------------------------------------ helpers
    def token_bytes(self) -> list[bytes]:
        return [self.expand(i) for i in range(len(self))]

    def coverage(self, texts: list[str]) -> float:
        """Fraction of corpus bytes that survive a round trip (sanity metric)."""
        total = ok = 0
        for t in texts:
            total += 1
            ok += int(self.decode(self.encode(t)) == t)
        return ok / max(1, total)
