import pytest
import tempfile
import os

@pytest.fixture
def app():
    import app as flask_app
    db_fd, db_path = tempfile.mkstemp()
    flask_app.app.config.update({
        "TESTING": True,
        "DATABASE": db_path,
        "SECRET_KEY": "test-secret",
    })
    with flask_app.app.app_context():
        from database import init_db
        init_db()
    yield flask_app.app
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def authed_client(client):
    client.post("/login", data={"password": "csfit2024"})
    return client
