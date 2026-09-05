"""Checkpoint recovery must reproduce the complete uninterrupted GA, not just its winner."""

import json

import pytest

from cmig.core.search_execution import SearchCancelled, SearchControl
from cmig.core.search_ga import GAConfig, genetic_search


@pytest.mark.parametrize("interrupt_at", [1, 7, 20, 38, 75])
def test_ga_checkpoint_resume_at_any_evaluation(interrupt_at):
    ids = [f"m{i:02}" for i in range(30)]
    config = GAConfig(pop_size=20, generations=50, max_evaluations=80, seed=7)

    def score(genome):
        return sum(int(member[1:]) / 7 for member in genome)

    expected = genetic_search(ids, score, config)
    state = {}
    calls = []

    def evaluate(genome):
        calls.append(genome)
        return score(genome)

    def save(snapshot):
        state.clear()
        state.update(json.loads(json.dumps(snapshot, allow_nan=False)))

    def check():
        if len(calls) >= interrupt_at:
            raise SearchCancelled()

    with pytest.raises(SearchCancelled):
        genetic_search(ids, evaluate, config, on_checkpoint=save, cancel_check=check)
    resumed = genetic_search(ids, evaluate, config, checkpoint_state=state)
    assert resumed == expected
    assert len(calls) == len(set(calls)) == 80


def test_batched_ga_is_identical_to_serial():
    ids = [f"m{i:02}" for i in range(40)]
    config = GAConfig(pop_size=20, max_evaluations=78, seed=11)

    def score(genome):
        return sum(int(member[1:]) for member in genome)

    expected = genetic_search(ids, score, config)
    actual = genetic_search(
        ids,
        score,
        config,
        batch_fitness_fn=lambda genomes: list(map(score, genomes)),
        batch_size=3,
    )
    assert actual == expected


def test_checkpoint_rejects_changed_input_and_preserves_file(tmp_path):
    path = tmp_path / "search.json"
    original = SearchControl(checkpoint=path)
    original.bind({"medium": "A"})
    original.save()
    saved = path.read_bytes()
    with pytest.raises(ValueError, match="mismatch"):
        SearchControl(checkpoint=path, resume=True).bind({"medium": "B"})
    with pytest.raises(ValueError, match="already exists"):
        SearchControl(checkpoint=path).bind({"medium": "A"})
    assert saved == path.read_bytes()


def test_checkpoint_has_exclusive_writer_lock(tmp_path):
    control = SearchControl(checkpoint=tmp_path / "state.json")
    with control.session():
        with pytest.raises(ValueError, match="checkpoint is in use"), control.session():
            pytest.fail("a second writer claimed the same checkpoint")
    assert not (tmp_path / "state.json.lock").exists()


def test_worker_failure_does_not_discard_prior_ordered_completion(monkeypatch):
    from concurrent.futures.process import BrokenProcessPool

    from cmig.service import search_service

    class Executor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def map(self, function, jobs):
            yield "completed first evaluation"
            raise BrokenProcessPool("injected worker exit")

    monkeypatch.setattr(search_service, "ProcessPoolExecutor", Executor)
    with search_service.search_workers(None, SearchControl(workers=2)) as evaluate:
        stream = evaluate([("a",), ("b",)])
        assert next(stream) == "completed first evaluation"
        with pytest.raises(ValueError, match="worker terminated"):
            next(stream)
