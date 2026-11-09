# Deploying Jenkins Alongside the News Feed API

**Author:** Kwesi Emprah
**Date:** November 2026
**Host:** AWS EC2 — Amazon Linux 2023, t3.micro, us-east-1
**Public IP:** 54.172.32.188

---

## Objective

Deploy Jenkins — an open-source CI/CD server — as a container on the same EC2 instance already hosting the containerized News Feed API, without disrupting the running API, and expose it securely.

This document records every step from SSH access through to a reachable, configured Jenkins instance, including the two problems encountered and how each was diagnosed.

---

## Final architecture

```
                        Internet
                           │
          ┌────────────────┴────────────────┐
          │                                 │
     port 80                           port 8080
   (open to all)                   (restricted to my IP)
          │                                 │
          ▼                                 ▼
   ┌──────────────────────────────────────────────┐
   │      EC2 Security Group (launch-wizard-2)    │
   │   22   → my IP      admin shell access       │
   │   80   → 0.0.0.0/0  public API               │
   │   8080 → my IP      Jenkins admin interface  │
   └──────────────────────────────────────────────┘
          │                                 │
          ▼                                 ▼
   ┌─────────────────┐              ┌─────────────────┐
   │  news-api       │              │  jenkins        │
   │  container      │              │  container      │
   │  host 80 → 8080 │              │  host 8080→8080 │
   │  stateless      │              │  volume-backed  │
   └─────────────────┘              └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │ Docker volume   │
                                    │ jenkins_home    │
                                    │ (survives the   │
                                    │  container)     │
                                    └─────────────────┘
```

Two containers, one host, one Docker engine. Each is published on a different host port, and each port has an inbound rule scoped to who actually needs it.

---

## Step 1 — SSH into the instance

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_assignment
ssh aws-server
```

`ssh-agent` holds the decrypted key for the session so the passphrase is entered once rather than on every connection. `aws-server` is a host alias defined in `~/.ssh/config`.

---

## Step 2 — Assess available resources

Jenkins is a Java application with substantial memory requirements. Before installing anything, the instance was measured.

```bash
free -h
df -h /
docker images
```

**Findings:**

| Resource | Value |
|---|---|
| Total memory | 916 MB |
| Available memory | 455 MB |
| Swap | **0 B — none configured** |
| Disk free | 4.8 GB of 8 GB |
| Orphaned images | one 158 MB dangling image |

**Assessment:** 455 MB of available memory is insufficient for Jenkins, which typically requires 512 MB–1 GB. With no swap configured, memory exhaustion would not degrade performance — it would trigger the kernel's out-of-memory killer, which selects a victim process by its own heuristics and could terminate the News Feed API rather than Jenkins.

This constraint was identified before deployment rather than discovered during an outage.

---

## Step 3 — Reclaim disk space

```bash
docker image prune -f
```

Removes dangling (unnamed, unreferenced) images left behind by previous rebuilds. Reported 0 B reclaimed because the orphaned image shared all its layers with the current one — the registry entry was removed, no duplicate data existed.

---

## Step 4 — Add swap space

Swap is disk space used as overflow when physical memory is exhausted. It is substantially slower than RAM, but it converts a fatal condition into a performance cost.

```bash
sudo fallocate -l 2G /swapfile     # create a 2 GB file
sudo chmod 600 /swapfile           # root-only: swap can contain anything from memory
sudo mkswap /swapfile              # format as swap
sudo swapon /swapfile              # activate
free -h                            # verify
```

**Make it persist across reboots:**

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
cat /etc/fstab
```

`/etc/fstab` defines what the system mounts at boot. Without this entry, swap would silently disappear on restart and the instance would return to its original failure mode.

> **Note on `tee -a`:** the `-a` flag appends. Without it, `tee` overwrites — which on `/etc/fstab` would destroy the instance's filesystem configuration.

**The `chmod 600` is a security control, not housekeeping.** Swap contains pages evicted from memory, which can include credentials, keys and session tokens. A world-readable swap file is a readable copy of whatever the system was holding in RAM.

---

## Step 5 — Open port 8080 to a single address

**AWS Console → EC2 → Security Groups → launch-wizard-2 → Edit inbound rules → Add rule**

| Field | Value |
|---|---|
| Type | Custom TCP |
| Port range | 8080 |
| Source | My IP |
| Description | Jenkins admin access |

**Resulting rule set:**

| Port | Service | Source | Justification |
|---|---|---|---|
| 22 | SSH | My IP /32 | Administrative shell. Single operator. |
| 80 | News API | 0.0.0.0/0 | Public API — public reachability is its purpose. |
| 8080 | Jenkins | My IP /32 | Administrative tool capable of arbitrary code execution. |

**Rationale for the Jenkins restriction:** Jenkins exists to execute commands on the host. Exposing it to the internet is functionally equivalent to publishing a remote shell. It receives the same treatment as SSH, for the same reason.

The three rules demonstrate that "least privilege" means matching each rule to the risk behind the port — not uniformly restricting or uniformly opening.

---

## Step 6 — Launch the Jenkins container

```bash
docker run -d \
  --name jenkins \
  --restart unless-stopped \
  -p 8080:8080 \
  -v jenkins_home:/var/jenkins_home \
  -e JAVA_OPTS="-Xmx512m" \
  jenkins/jenkins:lts
```

| Flag | Purpose |
|---|---|
| `-d` | Detached — survives SSH disconnection |
| `--name jenkins` | Stable reference name |
| `--restart unless-stopped` | Automatic recovery after crash or host reboot |
| `-p 8080:8080` | Publish host port 8080 to container port 8080 |
| `-v jenkins_home:/var/jenkins_home` | **Named volume for persistent state** |
| `-e JAVA_OPTS="-Xmx512m"` | Cap JVM heap at 512 MB |
| `jenkins/jenkins:lts` | Official image, long-term-support release line |

### Two deliberate configuration choices

**Heap cap.** The JVM will expand to consume available memory by default. On a 916 MB instance that risks starving the co-located API. Capping the heap bounds Jenkins' footprint and keeps the API's memory predictable.

**Port 50000 deliberately not published.** The Jenkins image declares port 50000 for inbound agent connections. This deployment has no remote agents, so the port was not published. `docker ps` confirms the distinction:

```
0.0.0.0:8080->8080/tcp,  50000/tcp
└── published, reachable  └── declared only, not reachable
```

Unused exposed ports are attack surface carried for no benefit.

### Why Jenkins requires a volume and the API does not

The News Feed API is stateless — all its data is compiled into the image. Destroying and recreating the container loses nothing.

Jenkins writes its entire operational state to `/var/jenkins_home`: the admin account, installed plugins, job definitions, build history, credentials. Containers are designed to be disposable; without external storage, every container replacement would reset Jenkins to a fresh installation.

A named Docker volume stores this data on the host filesystem, independent of any container lifecycle. The container becomes replaceable; the data does not.

---

## Step 7 — Retrieve the initial admin password

```bash
docker logs jenkins | tail -30
```

Or read it directly from the container:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Jenkins generates a one-time token on first boot and writes it only to the log and a file inside the container. This prevents an unconfigured instance from being claimed by whoever reaches it first — setup requires demonstrable access to the host.

> **Operational note:** container logs routinely contain secrets. Review before sharing or pasting log output.

---

## Step 8 — Complete the setup wizard

Browser: `http://54.172.32.188:8080`

1. **Unlock Jenkins** — paste the initial admin password
2. **Customize Jenkins** — Install suggested plugins (~80 plugins, 5–10 minutes on this hardware)
3. **Create First Admin User** — the initial token is invalidated at this point
4. **Instance Configuration** — accept `http://54.172.32.188:8080/`

**Memory observed throughout:**

| Stage | Used | Available | Swap used |
|---|---|---|---|
| API only (baseline) | 305 MB | 455 MB | 0 |
| Jenkins started | 564 MB | 196 MB | 52 MB |
| Plugin installation | 639 MB | **124 MB** | 78 MB |
| Jenkins idle (settled) | 647 MB | 119 MB | 84 MB |

Available memory fell to 124 MB during plugin installation while swap absorbed the overflow. Without the swap file added in Step 4, this stage would very likely have triggered the out-of-memory killer.

---

## Step 9 — Verify both services

**On the host:**

```bash
docker ps
docker volume ls
free -h
```

```
CONTAINER ID   IMAGE                 STATUS          PORTS                      NAMES
5c277595d350   jenkins/jenkins:lts   Up              0.0.0.0:8080->8080/tcp     jenkins
fc48458edafe   news-api              Up              0.0.0.0:80->8080/tcp       news-api

DRIVER    VOLUME NAME
local     jenkins_home
```

**From an external machine:**

```bash
curl http://54.172.32.188/health
# {"status":"ok"}
```

The API continued serving throughout the Jenkins deployment. No downtime was introduced.

---

## Step 10 — Verify persistence

Claiming a volume provides persistence is weaker than demonstrating it. The container was destroyed entirely and replaced:

```bash
docker rm -f jenkins

docker run -d \
  --name jenkins \
  --restart unless-stopped \
  -p 8080:8080 \
  -v jenkins_home:/var/jenkins_home \
  -e JAVA_OPTS="-Xmx512m" \
  jenkins/jenkins:lts
```

The new container received a different ID (`5c277595d350`, previously `4c616852a05c`), confirming it was newly created rather than restarted.

**Result:** reloading `http://54.172.32.188:8080` returned the **login page**, not the setup wizard. The admin account, installed plugins and all configuration survived the destruction of the container that created them.

---

## Problems encountered

### Problem 1 — Insufficient memory (anticipated)

**Detection:** `free -h` before deployment showed 455 MB available and no swap.

**Impact if unaddressed:** Jenkins startup or plugin installation would exhaust memory. With no swap, the kernel OOM killer would terminate a process — potentially the News Feed API rather than Jenkins.

**Resolution:** 2 GB swap file created and made persistent; Jenkins JVM heap capped at 512 MB.

**Verification:** peak usage reached 124 MB available with 78 MB of swap in use. Both services remained operational.

---

### Problem 2 — Jenkins unreachable after deployment

**Symptom:** browser returned `ERR_CONNECTION_TIMED_OUT` for `http://54.172.32.188:8080`.

**Diagnostic reasoning:** the error type identified the layer before any investigation.

| Error | Meaning | Implicated layer |
|---|---|---|
| **Connection timed out** | Packets silently dropped; nothing responded | Firewall / security group |
| Connection refused | Host responded; nothing listening on that port | Port mapping / application |

A timeout — combined with `docker ps` showing the container up and the log reporting `Jenkins is fully up and running` — ruled out the application, the container and the port mapping. The fault had to be at the network boundary.

**Root cause:** the security group inbound rule for port 8080 had not been saved. The console showed `Inbound rules (2)` — SSH and HTTP only.

**Resolution:** rule added and saved. Jenkins immediately reachable.

**Note:** the current IP was verified against the existing SSH rule first (`curl ifconfig.me` returned `24.34.178.176`, matching the working SSH rule), which eliminated a stale IP as the cause before looking further.

---

## Operations reference

```bash
# Status
docker ps                        # running containers
docker stats --no-stream         # live resource usage per container
free -h                          # host memory and swap

# Jenkins
docker logs jenkins              # application log
docker logs -f jenkins           # follow live
docker restart jenkins           # restart (data preserved by volume)
docker exec -it jenkins bash     # shell inside the container

# Volume
docker volume ls                 # list volumes
docker volume inspect jenkins_home   # host path and metadata

# Backup Jenkins data
docker run --rm \
  -v jenkins_home:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/jenkins-backup.tar.gz -C /data .
```

---

## Security posture

| Control | Implementation |
|---|---|
| Network exposure | Three inbound rules; only the public API is internet-facing |
| Administrative access | SSH and Jenkins both restricted to a single source IP |
| SSH authentication | Key-based only; password authentication and root login disabled |
| Container privilege | News API runs as a non-root user (`appuser`) |
| Unused ports | Jenkins agent port 50000 declared but not published |
| Swap file | Mode 600 — prevents reading memory contents from disk |
| Image scanning | Trivy runs against the API image on every pull request |
| Dependency scanning | pip-audit runs against pinned dependencies on every pull request |

---

## Known limitations

| Limitation | Impact | Remediation |
|---|---|---|
| **Instance undersized** | t3.micro (1 GB) is below Jenkins' comfortable minimum. Operating on swap; the UI is slow. | Resize to t3.small (2 GB) or larger. |
| **HTTP, not HTTPS** | Jenkins credentials traverse the network unencrypted. | Terminate TLS at a reverse proxy or load balancer with a certificate. |
| **Single-IP access control** | The operator's residential IP changes, requiring manual rule updates. | Whitelist a VPN or office egress range; or use a bastion host. |
| **No automated backup** | `jenkins_home` exists only on this instance's volume. | Scheduled volume backup to S3. |
| **Jenkins not yet integrated with CI** | GitHub Actions currently runs CI; Jenkins is deployed but idle. | Next phase of the project. |

---

## Summary

Jenkins 2.580.2 is deployed as a container on the same EC2 instance as the News Feed API, with persistent storage, automatic restart, a bounded memory footprint, and network access restricted to a single administrative source address. The API experienced no downtime during deployment and continues serving publicly.

| Service | URL | Access |
|---|---|---|
| News Feed API | http://54.172.32.188 | Public |
| API documentation | http://54.172.32.188/docs | Public |
| Jenkins | http://54.172.32.188:8080 | Restricted to operator IP |
