def test_login_redirects_to_cms_on_correct_password(client):
    response = client.post("/login", data={"password": "csfit2024"},
                           follow_redirects=False)
    assert response.status_code == 302
    assert "/cms" in response.headers["Location"]

def test_login_rejects_wrong_password(client):
    response = client.post("/login", data={"password": "wrong"})
    assert response.status_code == 200
    assert b"Incorrect password" in response.data

def test_cms_requires_auth(client):
    response = client.get("/cms", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_cms_accessible_when_authed(authed_client):
    response = authed_client.get("/cms")
    assert response.status_code == 200

def test_logout_clears_session(authed_client):
    authed_client.post("/logout")
    response = authed_client.get("/cms", follow_redirects=False)
    assert response.status_code == 302
