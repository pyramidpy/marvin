import pydantic_ai.models.test
import pytest


@pytest.fixture(autouse=True)
def prevent_model_requests():
    with pydantic_ai.models.override_allow_model_requests(False):
        yield


@pytest.fixture(autouse=True)
def set_test_model():
    model = pydantic_ai.models.test.TestModel()
