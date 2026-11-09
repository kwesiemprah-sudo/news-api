from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


# ---- /health ----

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---- /news ----

def test_news_returns_all_articles():
    response = client.get("/news")
    assert response.status_code == 200
    assert len(response.json()) == 12


def test_every_article_has_the_required_fields():
    required = {"id", "title", "summary", "source", "category", "published_at"}
    for article in client.get("/news").json():
        assert required.issubset(article.keys())


# ---- filtering ----

def test_category_filter():
    articles = client.get("/news?category=technology").json()
    assert len(articles) == 4
    assert all(a["category"] == "technology" for a in articles)


def test_category_filter_is_case_insensitive():
    lower = client.get("/news?category=technology").json()
    upper = client.get("/news?category=TECHNOLOGY").json()
    assert lower == upper


def test_limit():
    assert len(client.get("/news?limit=5").json()) == 5


def test_category_and_limit_combine():
    articles = client.get("/news?category=technology&limit=2").json()
    assert len(articles) == 2
    assert all(a["category"] == "technology" for a in articles)


def test_unknown_category_returns_empty_list():
    assert client.get("/news?category=nonsense").json() == []


def test_limit_below_one_is_rejected():
    assert client.get("/news?limit=0").status_code == 422


# ---- /news/{id} ----

def test_single_article():
    assert client.get("/news/1").json()["id"] == 1


def test_missing_article_returns_404():
    response = client.get("/news/999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_non_numeric_id_is_rejected():
    assert client.get("/news/banana").status_code == 422
