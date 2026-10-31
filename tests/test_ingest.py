from fpa.ingest import DATASETS, page_params


def test_paging_is_deterministic():
    p = page_params(100_000, 50_000)
    assert p == {"$limit": 50_000, "$offset": 100_000, "$order": ":id"}


def test_dataset_ids():
    assert DATASETS["expense_budget"].endswith("mwzb-yiwb.json")
    assert DATASETS["expense_funding"].endswith("39g5-gbp3.json")
