# News Feed API

A containerized News Feed API built with Python and FastAPI, deployed to an Amazon EC2 instance and reachable over the public internet.

**Author:** Kwesi Emprah

---

## Architecture

A request travels: browser → internet → EC2 public IP on port 80 → security group inbound rule permits it → Docker's port mapping forwards it to the container's port 8080 → uvicorn receives it → FastAPI routes it to the matching endpoint → the JSON response returns along the same path.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/news` | All articles (supports filtering) |
| GET | `/news/{id}` | A single article by id |
| GET | `/docs` | Interactive API documentation (auto-generated) |

### Query parameters on `/news`

| Parameter | Example | Effect |
|---|---|---|
| `category` | `/news?category=technology` | Only articles in that category |
| `limit` | `/news?limit=5` | At most that many articles |
| combined | `/news?category=technology&limit=2` | Both filters applied |

Available categories: `technology`, `business`, `science`, `sports`, `health`

### Example requests and responses

**GET /health**
```bash
curl http://<EC2_PUBLIC_IP>/health
```
```json
{"status": "ok"}
```

**GET /news?category=technology&limit=2**
```bash
curl "http://<EC2_PUBLIC_IP>/news?category=technology&limit=2"
```
```json
[
  {
    "id": 1,
    "title": "New Technology Changes the Way We Work",
    "summary": "Remote collaboration tools reshape the modern office.",
    "source": "Example News",
    "category": "technology",
    "published_at": "2026-08-08T12:00:00Z"
  },
  {
    "id": 4,
    "title": "Cybersecurity Firms Report Rise in Phishing",
    "summary": "Attackers increasingly target remote workers.",
    "source": "Secure Times",
    "category": "technology",
    "published_at": "2026-08-08T15:00:00Z"
  }
]
```

**GET /news/999** (article does not exist)
```bash
curl http://<EC2_PUBLIC_IP>/news/999
```
```json
{"detail": "Article 999 not found"}
```
Returns HTTP status `404`.

---

## Local Development

### Prerequisites
- Python 3.12+
- Docker

### Run without Docker
```bash
git clone <REPO_URL>
cd news-api

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Test it:
```bash
curl http://localhost:8080/health
curl http://localhost:8080/news
curl "http://localhost:8080/news?category=technology&limit=3"
```

### Build and run with Docker
```bash
docker build -t news-api .
docker run -d -p 8080:8080 --name news-api news-api
curl http://localhost:8080/health
```

---

## EC2 Deployment

### Instance configuration

| Setting | Value |
|---|---|
| Provider | AWS EC2 |
| AMI | Amazon Linux 2023 |
| Instance type | t3.micro |
| Region | us-east-1 |
| Public IP | `<EC2_PUBLIC_IP>` |

### Security group rules

| Type | Port | Source | Reason |
|---|---|---|---|
| SSH | 22 | My IP only | Administrative access, restricted to a single address |
| HTTP | 80 | 0.0.0.0/0 | Public API access — the service is intended to be public |

Only these two ports are open. All other inbound traffic is denied by default, following the principle of least privilege.

### SSH into the instance
```bash
ssh -i ~/.ssh/<your_key> <user>@<EC2_PUBLIC_IP>
```

### Install Docker on the instance
```bash
sudo dnf update -y
sudo dnf install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# log out and back in for the group change to apply
docker --version
```

### Deploy the container
```bash
git clone <REPO_URL>
cd news-api

docker build -t news-api .

docker run -d \
  --name news-api \
  --restart unless-stopped \
  -p 80:8080 \
  news-api
```

### Port mapping explained

Traffic arriving at the EC2 instance on port 80 is forwarded by Docker to port 8080 inside the container.

`--restart unless-stopped` ensures the container comes back automatically after a reboot or crash, so the API remains available after the SSH session ends.

### Verify from outside EC2
Run these from a machine other than the EC2 instance:
```bash
curl http://<EC2_PUBLIC_IP>/health
curl http://<EC2_PUBLIC_IP>/news
curl "http://<EC2_PUBLIC_IP>/news?category=technology"
curl http://<EC2_PUBLIC_IP>/news/1
curl -i http://<EC2_PUBLIC_IP>/news/999   # expect 404
```

---

## Useful operational commands

```bash
docker ps                      # running containers
docker logs news-api           # application logs
docker logs -f news-api        # follow logs live
docker stop news-api           # stop
docker start news-api          # start
docker restart news-api        # restart
docker rm -f news-api          # remove
```

---

## Final Public API Endpoint

| Resource | URL |
|---|---|
| Health check | `http://<EC2_PUBLIC_IP>/health` |
| News feed | `http://<EC2_PUBLIC_IP>/news` |
| Interactive docs | `http://<EC2_PUBLIC_IP>/docs` |

---

## Troubleshooting: works locally on EC2 but not from my laptop

Scenario: `curl localhost:8080/health` succeeds on the EC2 server, but `curl http://<PUBLIC_IP>/health` from a laptop fails.

Work outward from the application to the internet, eliminating one layer at a time.

**1. Application** — is the app itself running and healthy?
```bash
docker logs news-api
curl http://localhost:8080/health   # on the EC2 box
```
If this succeeds, the application layer is fine — the problem is further out.

**2. Docker** — is the container running, and is it bound correctly?
```bash
docker ps
```
Check the PORTS column. `0.0.0.0:80->8080/tcp` is correct. If it shows `127.0.0.1:80->8080/tcp`, Docker is only accepting local connections.

**3. Port mapping** — is the host listening on the expected port?
```bash
sudo ss -tlnp | grep -E ":80|:8080"
```
If nothing is listening on port 80, the `-p` mapping is wrong or missing. Also confirm the app binds to `0.0.0.0` and not `127.0.0.1` — binding to localhost inside the container makes it unreachable regardless of port mapping.

**4. EC2 host firewall** — is anything on the instance blocking traffic?
```bash
sudo iptables -L -n
```
Amazon Linux 2023 has no host firewall enabled by default, so this is usually clear — but it should be ruled out.

**5. Security group** — the most common cause.
Check the inbound rules in the AWS console. Port 80 must be allowed from `0.0.0.0/0`. A missing or overly narrow rule produces a hanging connection that eventually times out, rather than a refusal.

**6. Internet path** — client-side or network issues.
```bash
curl -v http://<PUBLIC_IP>/health
```
- Connection **timeout** points to the security group or network ACL blocking traffic silently.
- Connection **refused** points to nothing listening on the host — a Docker or port mapping problem.
- Also confirm you are using the **public** IP, not the private `172.31.x.x` address, and that the instance's public IP has not changed after a stop/start.

### Quick diagnostic summary

| Symptom | Most likely layer |
|---|---|
| `curl localhost` fails on EC2 | Application or Docker |
| `curl localhost` works, external times out | Security group |
| `curl localhost` works, external refused | Port mapping / bind address |
| Worked yesterday, fails today | Public IP changed after instance restart |

