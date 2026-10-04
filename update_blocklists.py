#!/usr/bin/env python3
"""Fusionne plusieurs listes de blocage IPv4 en deux fichiers : un pour le trafic
entrant (IN) et un pour le trafic sortant (OUT).

- Chaque liste est telechargee, nettoyee, dedoublonnee puis agregee (les IP deja
  couvertes par une plage sont supprimees, les plages voisines sont regroupees).
- Si une source est injoignable ou anormalement vide, la liste concernee n'est pas
  reecrite : l'ancienne version reste en place et le script sort en erreur.
- Aucune dependance : Python 3 standard uniquement.
"""
import ipaddress
import os
import sys
import time
import urllib.request

OUT_DIR = os.environ.get("OUT_DIR", "out")
MAX_ENTRIES = int(os.environ.get("MAX_ENTRIES", "100000"))  # limite Unifi par liste

LISTS = {
    "blocklist-in.txt": [
        "https://cinsscore.com/list/ci-badguys.txt",
        "https://iplists.firehol.org/files/firehol_level1.netset",
        "https://iplists.firehol.org/files/firehol_level2.netset",
        "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/ips/tif.txt",
        "https://raw.githubusercontent.com/stamparm/ipsum/master/levels/3.txt",
    ],
    "blocklist-out.txt": [
        "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/ips/tif.txt",
        "https://iplists.firehol.org/files/spamhaus_drop.netset",
    ],
}

# Adresses a ne JAMAIS bloquer, meme si une source les liste par erreur.
NEVER_BLOCK = {
    # Applique aux deux listes : resolveurs DNS publics
    "*": ["1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112"],
    # Applique a la liste OUT seulement : plages privees et reservees
    "blocklist-out.txt": [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/3",
    ],
}

MIN_PER_SOURCE = 50      # une source avec moins d'entrees est consideree comme cassee
MIN_PREFIX = 3           # refuse les plages plus larges que /3 (ex. 0.0.0.0/0)

_cache = {}


def download(url):
    if url in _cache:
        return _cache[url]
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "blocklist-merge/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            _cache[url] = text
            return text
        except Exception as exc:  # noqa: BLE001 - on retente quelle que soit l'erreur
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"telechargement impossible : {url} ({last})")


def parse(text):
    nets = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        token = line.split()[0].split(",")[0]
        try:
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        if net.version == 4 and net.prefixlen >= MIN_PREFIX:
            nets.append(net)
    return nets


def subtract(nets, excluded):
    """Retire les plages `excluded` d'une liste de reseaux deja agregee."""
    for ex in excluded:
        result = []
        for net in nets:
            if not net.overlaps(ex):
                result.append(net)
            elif net.subnet_of(ex):
                continue
            else:  # ex est strictement contenu dans net
                result.extend(net.address_exclude(ex))
        nets = result
    return nets


def build(name, urls):
    print(f"\n== {name}")
    merged = []
    for url in urls:
        nets = parse(download(url))
        print(f"  {len(nets):>7} entrees  {url}")
        if len(nets) < MIN_PER_SOURCE:
            raise RuntimeError(f"source anormalement courte ({len(nets)} entrees) : {url}")
        merged.extend(nets)

    raw = len(merged)
    nets = list(ipaddress.collapse_addresses(merged))
    excluded = [ipaddress.ip_network(x) for x in NEVER_BLOCK["*"] + NEVER_BLOCK.get(name, [])]
    nets = sorted(ipaddress.collapse_addresses(subtract(nets, excluded)))
    addresses = sum(n.num_addresses for n in nets)
    print(f"  {raw:>7} entrees au total -> {len(nets)} apres fusion ({addresses:,} adresses)")

    if len(nets) > MAX_ENTRIES:
        raise RuntimeError(f"{len(nets)} entrees : au-dessus de la limite de {MAX_ENTRIES}")

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with open(path + ".new", "w", encoding="utf-8", newline="\n") as fh:
        for net in nets:
            # une adresse seule s'ecrit sans /32
            fh.write((str(net.network_address) if net.prefixlen == 32 else str(net)) + "\n")
    os.replace(path + ".new", path)
    return raw, len(nets)


def main():
    failed = []
    summary = ["| Liste | Entrees brutes | Entrees publiees |", "|---|---|---|"]
    for name, urls in LISTS.items():
        try:
            raw, final = build(name, urls)
            summary.append(f"| {name} | {raw} | {final} |")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERREUR : {exc}", file=sys.stderr)
            summary.append(f"| {name} | echec | ancienne version conservee |")
            failed.append(name)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(summary) + "\n")

    if failed:
        print(f"\nListes non mises a jour : {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
