#!/usr/bin/env python3
"""
Failover DNS automatique OVH
=============================

Bascule un ou plusieurs enregistrements DNS (chez OVH) entre deux IP fixes
(par exemple ta Freebox et ta Livebox) selon leur disponibilité réelle,
testée depuis l'extérieur.

Logique :
  - teste si l'IP actuellement pointée par le DNS répond encore
  - si non, bascule vers l'autre IP si elle répond
  - si aucune des deux ne répond, ne touche à rien et envoie une alerte
  - si FAILBACK_TO_PRIMARY=true (par défaut), repasse automatiquement sur
    l'IP primaire dès qu'elle est de nouveau saine

Toute la configuration se fait par variables d'environnement (voir README.md).
"""

import os
import socket
import sys
import time
import urllib.request

import ovh

# ---------------------------------------------------------------------------
# Configuration (variables d'environnement)
# ---------------------------------------------------------------------------

OVH_ENDPOINT = os.environ.get("OVH_ENDPOINT", "ovh-eu")
OVH_APPLICATION_KEY = os.environ["OVH_APPLICATION_KEY"]
OVH_APPLICATION_SECRET = os.environ["OVH_APPLICATION_SECRET"]
OVH_CONSUMER_KEY = os.environ["OVH_CONSUMER_KEY"]

IP_PRIMARY = os.environ["IP_PRIMARY"]      # IP fixe Free
IP_SECONDARY = os.environ["IP_SECONDARY"]  # IP fixe Orange

# Liste des enregistrements à surveiller / mettre à jour.
# Format : "zone1.fr:@,zone1.fr:jellyfin,zone2.fr:@"
# "@" désigne la racine du domaine (sous-domaine vide côté OVH).
RECORDS_RAW = os.environ["RECORDS"]

HEALTHCHECK_PORT = int(os.environ.get("HEALTHCHECK_PORT", "443"))
HEALTHCHECK_TIMEOUT = float(os.environ.get("HEALTHCHECK_TIMEOUT", "5"))
HEALTHCHECK_ATTEMPTS = int(os.environ.get("HEALTHCHECK_ATTEMPTS", "3"))
HEALTHCHECK_DELAY = float(os.environ.get("HEALTHCHECK_DELAY", "2"))

FAILBACK_TO_PRIMARY = os.environ.get("FAILBACK_TO_PRIMARY", "true").lower() == "true"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # ex: https://ntfy.sh/mon-topic-secret


def parse_records(raw):
    records = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        zone, sub = item.split(":", 1)
        sub = "" if sub.strip() == "@" else sub.strip()
        records.append((zone.strip(), sub))
    return records


def tcp_check(ip, port, timeout):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_ip(ip, port, attempts, timeout, delay):
    for i in range(attempts):
        if tcp_check(ip, port, timeout):
            return True
        if i < attempts - 1:
            time.sleep(delay)
    return False


def notify(message):
    print(message)
    if not WEBHOOK_URL:
        return
    try:
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=message.encode("utf-8"),
            headers={"Title": "OVH Failover"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Notification echouee : {exc}")


def get_record(client, zone, subdomain):
    ids = client.get(
        f"/domain/zone/{zone}/record",
        fieldType="A",
        subDomain=subdomain,
    )
    if not ids:
        raise RuntimeError(
            f"Aucun enregistrement A trouve pour {subdomain or '@'}.{zone}"
        )
    record_id = ids[0]
    record = client.get(f"/domain/zone/{zone}/record/{record_id}")
    return record_id, record["target"]


def set_record(client, zone, record_id, new_target):
    client.put(f"/domain/zone/{zone}/record/{record_id}", target=new_target)
    client.post(f"/domain/zone/{zone}/refresh")


def decide_target(current, primary_ok, secondary_ok):
    if current == IP_PRIMARY:
        if primary_ok:
            return IP_PRIMARY
        if secondary_ok:
            return IP_SECONDARY
        return current
    if current == IP_SECONDARY:
        if FAILBACK_TO_PRIMARY and primary_ok:
            return IP_PRIMARY
        if secondary_ok:
            return IP_SECONDARY
        if primary_ok:
            return IP_PRIMARY
        return current
    # Cible actuelle ni Free ni Orange (premiere execution, ou config manuelle) :
    # on choisit la meilleure IP disponible, priorite au primaire.
    if primary_ok:
        return IP_PRIMARY
    if secondary_ok:
        return IP_SECONDARY
    return current


def main():
    records = parse_records(RECORDS_RAW)
    if not records:
        print("Aucun enregistrement configure (variable RECORDS vide).")
        sys.exit(1)

    print(
        f"Test de {IP_PRIMARY} (primaire) et {IP_SECONDARY} (secondaire) "
        f"sur le port {HEALTHCHECK_PORT}..."
    )
    primary_ok = check_ip(
        IP_PRIMARY, HEALTHCHECK_PORT, HEALTHCHECK_ATTEMPTS,
        HEALTHCHECK_TIMEOUT, HEALTHCHECK_DELAY,
    )
    secondary_ok = check_ip(
        IP_SECONDARY, HEALTHCHECK_PORT, HEALTHCHECK_ATTEMPTS,
        HEALTHCHECK_TIMEOUT, HEALTHCHECK_DELAY,
    )
    print(f"  Primaire   ({IP_PRIMARY}) : {'OK' if primary_ok else 'DOWN'}")
    print(f"  Secondaire ({IP_SECONDARY}) : {'OK' if secondary_ok else 'DOWN'}")

    if not primary_ok and not secondary_ok:
        notify(
            f"ALERTE : ni {IP_PRIMARY} (Free) ni {IP_SECONDARY} (Orange) "
            f"ne repondent sur le port {HEALTHCHECK_PORT}. Verifie ta connexion !"
        )

    client = ovh.Client(
        endpoint=OVH_ENDPOINT,
        application_key=OVH_APPLICATION_KEY,
        application_secret=OVH_APPLICATION_SECRET,
        consumer_key=OVH_CONSUMER_KEY,
    )

    for zone, subdomain in records:
        label = f"{subdomain or '@'}.{zone}"
        try:
            record_id, current_target = get_record(client, zone, subdomain)
        except Exception as exc:  # noqa: BLE001
            print(f"[erreur] {label} : impossible de lire l'enregistrement ({exc})")
            continue

        target = decide_target(current_target, primary_ok, secondary_ok)

        if target == current_target:
            print(f"  {label} : reste sur {current_target}")
            continue

        try:
            set_record(client, zone, record_id, target)
            print(f"  {label} : {current_target} -> {target}")
            notify(f"Bascule DNS : {label} de {current_target} vers {target}")
        except Exception as exc:  # noqa: BLE001
            print(f"[erreur] {label} : echec de la mise a jour ({exc})")
            notify(f"Echec de bascule pour {label} : {exc}")


if __name__ == "__main__":
    main()
