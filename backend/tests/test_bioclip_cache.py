"""The classifier's per-species text-embedding cache, with a stand-in model
(the real one is never loaded in tests)."""

import pytest
import torch

from app.dao import bioclip_classifier


class _FakeModel:
    def __init__(self):
        self.texts_encoded = []

    def encode_text(self, tokens):
        self.texts_encoded.extend(tokens)
        # Deterministic, distinct vector per text.
        return torch.stack([torch.tensor([float(len(t)), float(sum(map(ord, t)) % 97), 1.0]) for t in tokens])


@pytest.fixture()
def fake_model(monkeypatch):
    model = _FakeModel()
    tokenizer = lambda texts: list(texts)  # noqa: E731 — identity "tokenizer"
    monkeypatch.setattr(bioclip_classifier, "_get_model", lambda: (model, tokenizer, None))
    monkeypatch.setattr(bioclip_classifier, "_species_feature_cache", {})
    return model


def _sp(code, name):
    return {"species_code": code, "common_name": name, "scientific_name": name}


def test_only_uncached_species_are_encoded(fake_model):
    templates = len(bioclip_classifier._TEMPLATES)
    bioclip_classifier._get_text_features([_sp("a", "Alpha"), _sp("b", "Beta")])
    assert len(fake_model.texts_encoded) == 2 * templates

    bioclip_classifier._get_text_features([_sp("b", "Beta"), _sp("c", "Gamma")])

    # Only Gamma was new.
    assert len(fake_model.texts_encoded) == 3 * templates


def test_features_line_up_with_deduped_pool(fake_model):
    features, pool = bioclip_classifier._get_text_features(
        [_sp("a", "Alpha"), _sp("b", "Beta"), _sp("a", "Alpha again")]
    )

    assert [c["species_code"] for c in pool] == ["a", "b"]
    assert features.shape == (3, 2)
    # Each column is unit length, and matches what's cached for that species.
    assert torch.allclose(features.norm(dim=0), torch.ones(2))
    assert torch.equal(features[:, 1], bioclip_classifier._species_feature_cache["b"])


def test_batched_encoding_matches_one_at_a_time(fake_model, monkeypatch):
    monkeypatch.setattr(bioclip_classifier, "_ENCODE_BATCH_TEXTS", 3)  # force several batches
    species = [_sp(str(i), f"Bird number {i}") for i in range(5)]
    features, _ = bioclip_classifier._get_text_features(species)

    # The original per-species math: normalize each template, average, renormalize.
    for i, s in enumerate(species):
        texts = [t(s["common_name"]) for t in bioclip_classifier._TEMPLATES]
        emb = torch.nn.functional.normalize(fake_model.encode_text(texts), dim=-1).mean(dim=0)
        assert torch.allclose(features[:, i], emb / emb.norm())


def test_saved_embeddings_round_trip(fake_model, monkeypatch, tmp_path):
    monkeypatch.setattr(bioclip_classifier, "_EMBEDDINGS_FILE", tmp_path / "emb.pt")
    bioclip_classifier._get_text_features([_sp("a", "Alpha"), _sp("b", "Beta")])
    bioclip_classifier.save_embeddings()
    saved = dict(bioclip_classifier._species_feature_cache)

    monkeypatch.setattr(bioclip_classifier, "_species_feature_cache", {})
    assert bioclip_classifier._load_saved_embeddings() == 2
    assert all(torch.equal(bioclip_classifier._species_feature_cache[k], v) for k, v in saved.items())


def test_saved_embeddings_from_another_model_are_ignored(fake_model, monkeypatch, tmp_path):
    path = tmp_path / "emb.pt"
    torch.save({"model_id": "some-other-model", "templates": 2, "embeddings": {"a": torch.ones(3)}}, path)
    monkeypatch.setattr(bioclip_classifier, "_EMBEDDINGS_FILE", path)

    assert bioclip_classifier._load_saved_embeddings() == 0
    assert bioclip_classifier._species_feature_cache == {}


def test_missing_embeddings_file_is_fine(fake_model, monkeypatch, tmp_path):
    monkeypatch.setattr(bioclip_classifier, "_EMBEDDINGS_FILE", tmp_path / "nope.pt")
    assert bioclip_classifier._load_saved_embeddings() == 0
