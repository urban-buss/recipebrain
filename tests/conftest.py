from __future__ import annotations

import pytest

from recipebrain.query import invalidate_connection
from tests.dataset_factory import make_recipe, make_source, write_dataset


@pytest.fixture(autouse=True)
def _clear_conn_cache():
    """Ensure each test starts with a fresh connection cache."""
    invalidate_connection()
    yield
    invalidate_connection()


@pytest.fixture
def settings_defaults():
    from recipebrain.settings import Settings

    return Settings.load(None)


@pytest.fixture
def populated_output(tmp_path):
    """Write a minimal valid dataset and return the output directory."""
    output = tmp_path / "output"
    output.mkdir()
    write_dataset(
        output,
        sources=[make_source()],
        recipes=[
            make_recipe(id=1, title="Pasta Carbonara", title_normalised="pasta carbonara"),
            make_recipe(
                id=2,
                title="Risotto",
                title_normalised="risotto",
                source_url="https://fooby.ch/r/2",
                source_external_id="r2",
            ),
        ],
    )
    return output
