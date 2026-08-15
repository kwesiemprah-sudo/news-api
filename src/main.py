from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List

app = FastAPI(
    title="News Feed API",
    description="A simple containerized news feed API",
    version="1.0.0"
)

# In-memory news data store
ARTICLES = [
    {"id": 1,  "title": "New Technology Changes the Way We Work",
     "summary": "Remote collaboration tools reshape the modern office.",
     "source": "Example News", "category": "technology",
     "published_at": "2026-08-08T12:00:00Z"},
    {"id": 2,  "title": "Markets Rally After Central Bank Decision",
     "summary": "Investors respond positively to the latest rate announcement.",
     "source": "Finance Daily", "category": "business",
     "published_at": "2026-08-08T13:30:00Z"},
    {"id": 3,  "title": "Breakthrough in Renewable Energy Storage",
     "summary": "Researchers report a major gain in battery efficiency.",
     "source": "Science Wire", "category": "science",
     "published_at": "2026-08-08T14:15:00Z"},
    {"id": 4,  "title": "Cybersecurity Firms Report Rise in Phishing",
     "summary": "Attackers increasingly target remote workers.",
     "source": "Secure Times", "category": "technology",
     "published_at": "2026-08-08T15:00:00Z"},
    {"id": 5,  "title": "National Team Advances to Final",
     "summary": "A late goal secures a place in the championship match.",
     "source": "Sports Report", "category": "sports",
     "published_at": "2026-08-08T16:45:00Z"},
    {"id": 6,  "title": "Cloud Providers Expand Regional Capacity",
     "summary": "New data centres announced across three continents.",
     "source": "Example News", "category": "technology",
     "published_at": "2026-08-08T17:20:00Z"},
    {"id": 7,  "title": "Health Study Links Sleep and Productivity",
     "summary": "Consistent rest correlates with improved focus at work.",
     "source": "Health Journal", "category": "health",
     "published_at": "2026-08-08T18:05:00Z"},
    {"id": 8,  "title": "Small Businesses Adopt Digital Payments",
     "summary": "Contactless transactions continue to grow year on year.",
     "source": "Finance Daily", "category": "business",
     "published_at": "2026-08-08T19:10:00Z"},
    {"id": 9,  "title": "Space Agency Confirms Launch Window",
     "summary": "The next resupply mission is scheduled for early autumn.",
     "source": "Science Wire", "category": "science",
     "published_at": "2026-08-08T20:00:00Z"},
    {"id": 10, "title": "City Marathon Draws Record Entries",
     "summary": "Organisers report the largest field in the event's history.",
     "source": "Sports Report", "category": "sports",
     "published_at": "2026-08-08T21:30:00Z"},
    {"id": 11, "title": "Open Source Project Reaches Major Milestone",
     "summary": "The community celebrates its ten-thousandth contribution.",
     "source": "Example News", "category": "technology",
     "published_at": "2026-08-08T22:00:00Z"},
    {"id": 12, "title": "Nutrition Guidelines Updated for 2026",
     "summary": "Health authorities revise daily intake recommendations.",
     "source": "Health Journal", "category": "health",
     "published_at": "2026-08-08T23:15:00Z"},
]


@app.get("/health")
def health_check():
    """Liveness probe used to confirm the service is running."""
    return {"status": "ok"}


@app.get("/news")
def get_news(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum articles to return"),
):
    """Return the news feed, optionally filtered by category and limited in size."""
    results: List[dict] = ARTICLES

    if category:
        results = [a for a in results if a["category"].lower() == category.lower()]

    if limit:
        results = results[:limit]

    return results


@app.get("/news/{article_id}")
def get_article(article_id: int):
    """Return a single article by its id, or 404 if it does not exist."""
    for article in ARTICLES:
        if article["id"] == article_id:
            return article
    raise HTTPException(status_code=404, detail=f"Article {article_id} not found")