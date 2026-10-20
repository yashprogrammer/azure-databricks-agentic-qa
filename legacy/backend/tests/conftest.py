import os
import tempfile

import pytest

# Point the app at a throwaway database before any app module is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/filings"


@pytest.fixture()
def login():
    """login(client, email) -> Authorization header for that user, via the development IdP."""

    def _login(client, email: str) -> dict:
        r = client.post("/dev-idp/token", json={"username": email, "password": "contoso-dev"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
