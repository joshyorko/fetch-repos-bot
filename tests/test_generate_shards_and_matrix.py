import json
from pathlib import Path

import scripts.generate_shards_and_matrix as gsm


def setup_work_items(tmp_path: Path, items):
    producer_dir = tmp_path / "output" / "producer-to-consumer"
    producer_dir.mkdir(parents=True)
    with open(producer_dir / "work-items.json", "w") as f:
        json.dump(items, f)


def read_matrix(tmp_path: Path):
    with open(tmp_path / "output" / "matrix-output.json", "r") as f:
        return json.load(f)


def read_shard(tmp_path: Path, shard_id: int):
    with open(tmp_path / "output" / "shards" / f"work-items-shard-{shard_id}.json") as f:
        return json.load(f)


def test_no_items(tmp_path, monkeypatch):
    setup_work_items(tmp_path, [])
    monkeypatch.chdir(tmp_path)
    gsm.main(4)
    assert read_matrix(tmp_path) == {"matrix": {"include": []}}


def test_fewer_items_than_workers(tmp_path, monkeypatch):
    items = [1, 2]
    setup_work_items(tmp_path, items)
    monkeypatch.chdir(tmp_path)
    gsm.main(5)
    matrix = read_matrix(tmp_path)
    assert len(matrix["matrix"]["include"]) == 2
    assert read_shard(tmp_path, 0) == [1]
    assert read_shard(tmp_path, 1) == [2]


def test_more_items_than_workers(tmp_path, monkeypatch):
    items = list(range(5))
    setup_work_items(tmp_path, items)
    monkeypatch.chdir(tmp_path)
    gsm.main(2)
    matrix = read_matrix(tmp_path)
    assert len(matrix["matrix"]["include"]) == 2
    assert read_shard(tmp_path, 0) == [0, 1, 2]
    assert read_shard(tmp_path, 1) == [3, 4]
