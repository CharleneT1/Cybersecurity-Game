# Cybersecurity-Game

This repository contains a prototype educational cyber-attack strategy game inspired by _Plague Inc._. The player takes the attacker's side: pick a live target on the world map, choose which unlocked attack to launch at it based on its device type and vulnerability score, and successful hits unlock that device's neighbors as new targets.

## Features

- **Attacker choice, not autoplay.** Two starting endpoints are reachable targets; everything else is locked. Click a live (amber) target to open its attack picker.
- **Attack Tree.** A prerequisite tree (mirrors the defense Upgrade Tree's UI) where points unlock reusable attacks -- Credential Guessing, Phishing Link, Exploit Kit, Zero-Day Broker -- each favored against specific device types.
- **Per-device vulnerability scoring.** Every node has a 1-10 vulnerability score with a short reasoning string, shown in its tooltip and attack panel. A favored attack always succeeds; an unfavored one still has real odds against a soft (high-scoring) target instead of a flat auto-fail.
- **Progressive unlocking.** Successfully compromising a node unlocks its real network neighbors (from the same connection graph used for the visible links) as new targets and pays out attack points.
- World map background is a precision-generated equirectangular map (Natural Earth coastline data, exact 2:1 projection) committed at `assets/world_map.png`, scaled beneath an on-screen navigation bar with regional labels. Node placement is validated against traced coastline polygons independently of the image, so land and nodes can't drift out of alignment (see `assets/README.md`).
- Ten curated device nodes anchored to real-world metropolitan hubs with land-validated placement and scenario-specific lore, each with unique metadata (device class, connectivity mix, focus area) on hover.
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

Click a highlighted (amber) node to attack it -- you'll need at least one unlocked attack from the "Attacks" menu first. Close the window or press `Alt+F4`/`Cmd+W` to quit.

## Next steps

From the original hackathon design notes, not yet built:

- A victim social-media/OSINT screen (reviewing a target's public posts before choosing a credential-guessing angle).
- A dedicated credential-guessing mini-interaction (username/password guess screen), rather than resolving it as a single attack-tree click.
- Transmission-vector types (Bluetooth, home network, public Wi-Fi) as a distinct choice from the attack/exploit type.
- A general scoring table (infectivity / severity / comms) summarizing a run, beyond the current integrity percentage.

The code is organized so each of these can layer onto the existing target/attack-tree panels without reworking the core loop.
