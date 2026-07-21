# Cybersecurity-Game

This repository contains a prototype educational cyber-attack strategy game inspired by _Plague Inc._. The player takes the attacker's side: pick a live target on the world map, choose which unlocked attack to launch at it based on its device type and vulnerability score, and successful hits unlock that device's neighbors as new targets.

## Features

- **Tutorial gate: Sara's Laptop.** The game opens on a single OSINT/social-engineering puzzle, not the map. Sara's public posts (job announcement, a pet's birthday) are shown next to a login form for her work account; her email is spelled out in one post, her password pattern (pet name + age) in another. A first honest guess gets partial feedback ("username's right, password's wrong") instead of a full giveaway.
- **Sara's Laptop is a real node, not a cutscene.** Logging in marks her device "infected" on the actual map graph -- it's node 11, connected to Madrid and Barcelona exactly like any other device, and those two unlock through the same `unlock_neighbors()` mechanism a later compromise uses. Hovering her node afterward shows the same tooltip (device type, vulnerability score, status) as everything else.
- **Attacker choice, not autoplay.** Madrid and Barcelona become reachable targets once Sara's laptop is compromised; everything else is locked. Click a live (amber) target to open its attack picker.
- **Attack Tree.** A prerequisite tree (mirrors the defense Upgrade Tree's UI) where points unlock reusable attacks -- Credential Guessing, Phishing Link, Exploit Kit, Zero-Day Broker -- each favored against specific device types.
- **Per-device vulnerability scoring.** Every node has a 1-10 vulnerability score with a short reasoning string, shown in its tooltip and attack panel. A favored attack always succeeds; an unfavored one still has real odds against a soft (high-scoring) target instead of a flat auto-fail.
- **Progressive unlocking.** Successfully compromising a node unlocks its real network neighbors (from the same connection graph used for the visible links) as new targets and pays out attack points.
- World map background is a precision-generated equirectangular map (Natural Earth coastline data, exact 2:1 projection) committed at `assets/world_map.png`, scaled beneath an on-screen navigation bar with regional labels. Node placement is validated against traced coastline polygons independently of the image, so land and nodes can't drift out of alignment (see `assets/README.md`).
- Eleven curated device nodes anchored to real-world metropolitan hubs with land-validated placement and scenario-specific lore, each with unique metadata (device class, connectivity mix, focus area) on hover.
- Visible network links trace sensible connectivity paths (municipal Wi-Fi, VPN tunnels, fiber), color-coded green/red and annotated on hover with the link's purpose and security posture.
- Heads-up display tracks reachable targets, infected count, still-locked count, network integrity, and current attack points.
- A separate defense Upgrade Tree (Awareness Campaigns, Patch Automation, Network Segmentation, ...) is still in place from the original build.

## Requirements

- Python 3.9+
- [pygame](https://www.pygame.org/) (`pip install pygame`)

## Running the prototype

```bash
python3 main.py
```

Solve the Sara's Laptop login first (OSINT her posts on the left for the real username and password), then click a highlighted (amber) node on the map to attack it -- you'll need at least one unlocked attack from the "Attacks" menu first. Close the window or press `Alt+F4`/`Cmd+W` to quit.

## Next steps

From the original hackathon design notes, not yet built:

- **Multi-hit targets:** some devices may need more than one successful attack to fully compromise, instead of every hit being single-shot.
- A richer OSINT puzzle with decoy details and multiple guess attempts (the current tutorial is the focused version: one clean clue per credential).
- Transmission-vector types (Bluetooth, home network, public Wi-Fi) as a distinct choice from the attack/exploit type.
- A general scoring table (infectivity / severity / comms) summarizing a run, beyond the current integrity percentage.

The code is organized so each of these can layer onto the existing target/attack-tree panels without reworking the core loop.
