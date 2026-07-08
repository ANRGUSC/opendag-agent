import pytest

from opendag.presets import default_network


@pytest.fixture
def network():
    return default_network(sites=3)
