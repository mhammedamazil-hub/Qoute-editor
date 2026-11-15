import numpy as np
from minicoder.nano import NanoLM, NanoConfig


def test_training_reduces_loss(brain_home):
    corpus = ["def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n" * 40]
    model = NanoLM(NanoConfig(context=8, embed_dim=8, hidden=64))
    before = model.perplexity(corpus)
    stats = model.train_on_texts(corpus, steps=120, batch_size=16, lr=5e-3, log_every=0)
    after = model.perplexity(corpus)
    assert stats["final_loss"] < stats["initial_loss"]
    assert after < before


def test_save_load_roundtrip(brain_home, tmp_path):
    model = NanoLM(NanoConfig(context=8, embed_dim=8, hidden=32))
    out = model.save(tmp_path / "nano_test.npz")
    clone = NanoLM.load(out)
    assert clone.cfg.context == model.cfg.context
    assert clone.cfg.hidden == model.cfg.hidden
    import numpy as np
    assert np.allclose(clone.W2, model.W2)


def test_generate_produces_text(brain_home):
    model = NanoLM(NanoConfig(context=8, embed_dim=8, hidden=32))
    model.train_on_texts(["abc123" * 50], steps=5, batch_size=4, log_every=0)
    out = model.generate("abc", max_bytes=16, seed=1)
    assert isinstance(out, str) and len(out) >= 3
