#!/usr/bin/env python3
"""Retire des blocklists toutes les plages listees dans allowlist.txt.

- Une entree entierement comprise dans une plage autorisee est supprimee.
- Une entree plus large qui contient une plage autorisee est decoupee :
  on garde tout sauf la partie autorisee (le blocage du reste est conserve).
- Les lignes qui ne sont pas des IP/CIDR (commentaires...) sont laissees telles quelles.
- Un fichier n'est reecrit que s'il a change.
"""
import ipaddress
import sys
from pathlib import Path

ALLOWLIST = Path("allowlist.txt")
LISTES = [Path("blocklist-in.txt"), Path("blocklist-out.txt")]
LIMITE_UNIFI = 100_000  # entrees max par network group UniFi


def charger_allowlist():
    reseaux = []
    for numero, ligne in enumerate(ALLOWLIST.read_text().splitlines(), 1):
        valeur = ligne.split("#", 1)[0].strip()
        if not valeur:
            continue
        try:
            reseaux.append(ipaddress.ip_network(valeur, strict=False))
        except ValueError:
            print(f"allowlist.txt ligne {numero} ignoree (invalide) : {valeur}")
    return reseaux


def soustraire(reseau, autorises):
    restes = [reseau]
    for autorise in autorises:
        if autorise.version != reseau.version:
            continue
        suivants = []
        for r in restes:
            if not r.overlaps(autorise):
                suivants.append(r)
            elif r.subnet_of(autorise):
                pass  # entierement autorise : on retire
            else:
                suivants.extend(r.address_exclude(autorise))  # on decoupe
        restes = suivants
    return restes


def filtrer(fichier, autorises):
    lignes = fichier.read_text().splitlines()
    sortie, retirees, decoupees = [], 0, 0
    for ligne in lignes:
        valeur = ligne.strip()
        try:
            reseau = ipaddress.ip_network(valeur, strict=False)
        except ValueError:
            sortie.append(ligne)
            continue
        restes = soustraire(reseau, autorises)
        if restes == [reseau]:
            sortie.append(ligne)
        elif not restes:
            retirees += 1
            print(f"  retire  : {valeur}")
        else:
            decoupees += 1
            print(f"  decoupe : {valeur} -> {len(restes)} plages")
            sortie.extend(str(r) for r in sorted(restes))

    nb_ip = sum(1 for l in sortie if l.strip() and not l.lstrip().startswith("#"))
    if nb_ip > LIMITE_UNIFI:
        print(f"  ATTENTION : {nb_ip} entrees, au-dessus de la limite UniFi ({LIMITE_UNIFI})")

    if sortie != lignes:
        fichier.write_text("\n".join(sortie) + "\n")
    print(f"{fichier} : {retirees} retiree(s), {decoupees} decoupee(s), {nb_ip} entrees")


def main():
    if not ALLOWLIST.exists():
        print("Pas de allowlist.txt : rien a exclure")
        return 0
    autorises = charger_allowlist()
    print(f"{len(autorises)} plage(s) autorisee(s)")
    for fichier in LISTES:
        if fichier.exists():
            filtrer(fichier, autorises)
        else:
            print(f"{fichier} absent, ignore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
