# Failover DNS automatique Free / Orange via l'API OVH

Ce script teste, toutes les 5 minutes, si ton serveur répond encore sur ton
IP Free ou sur ton IP Orange, et bascule automatiquement le(s)
enregistrement(s) DNS chez OVH sur l'IP qui fonctionne.

## Fichiers

- `ovh_failover.py` — le script
- `.github/workflows/failover.yml` — l'automatisation (exécution planifiée gratuite via GitHub Actions)

## 1. Créer un token d'API OVH

Va sur cette page, qui pré-remplit les droits pour tes 3 domaines (si le
formulaire ne garde qu'une ligne par méthode, ajoute les 2 autres domaines à
la main avec le bouton "+") :

```
https://eu.api.ovh.com/createToken/index.cgi?GET=/domain/zone/marceau-rodrigues.fr/*&PUT=/domain/zone/marceau-rodrigues.fr/*&POST=/domain/zone/marceau-rodrigues.fr/*&GET=/domain/zone/moanin.fr/*&PUT=/domain/zone/moanin.fr/*&POST=/domain/zone/moanin.fr/*&GET=/domain/zone/trainizer.fr/*&PUT=/domain/zone/trainizer.fr/*&POST=/domain/zone/trainizer.fr/*
```

- Connecte-toi avec ton compte OVH
- **Nom du script** : par exemple `failover-dns`
- **Validité** : illimitée
- Valide

Tu obtiens trois valeurs à copier précieusement : `Application Key`,
`Application Secret`, `Consumer Key`.

## 2. Créer le dépôt GitHub

- Crée un dépôt **privé** sur GitHub (les secrets restent privés même sur un
  dépôt public, mais autant rester prudent)
- Dépose-y `ovh_failover.py` et `.github/workflows/failover.yml` (en
  respectant bien l'arborescence du dossier `.github/workflows/`)

## 3. Configurer les secrets

Dans le dépôt : **Settings → Secrets and variables → Actions → New repository
secret**, crée :

| Nom | Valeur |
|---|---|
| `OVH_APPLICATION_KEY` | obtenue à l'étape 1 |
| `OVH_APPLICATION_SECRET` | obtenue à l'étape 1 |
| `OVH_CONSUMER_KEY` | obtenue à l'étape 1 |
| `IP_PRIMARY` | ton IP fixe Free |
| `IP_SECONDARY` | ton IP fixe Orange |
| `WEBHOOK_URL` *(optionnel)* | voir section notifications ci-dessous |

## 4. Couvrir tous les sous-domaines (wildcard)

Pas besoin de lister chaque sous-domaine un par un. La ligne `RECORDS` est
déjà configurée avec la racine (`@`) et le wildcard (`*`) pour tes 3
domaines :

```
RECORDS: "marceau-rodrigues.fr:@,marceau-rodrigues.fr:*,moanin.fr:@,moanin.fr:*,trainizer.fr:@,trainizer.fr:*"
```

Un enregistrement `*.domaine.fr` couvre tout sous-domaine qui n'a pas déjà
son propre enregistrement explicite (ex: `jellyfin.moanin.fr` sera couvert
automatiquement). **Trois limites à connaître :**

- **Le script ne crée pas ces enregistrements, il les met à jour.** Si le
  wildcard `*` (ou la racine `@`) n'existe pas encore dans la zone DNS d'un
  domaine, va d'abord le créer manuellement une fois dans l'espace client
  OVH (Zone DNS → Ajouter une entrée → Type A → sous-domaine `*` → cible =
  ton IP Free actuelle). Ensuite le script prendra le relais.
- **Un sous-domaine avec un enregistrement spécifique prend le pas sur le
  wildcard.** S'il existe déjà une entrée dédiée pour un sous-domaine
  particulier (ex: un `mail.` géré par un autre service, ou un sous-domaine
  Trainizer hébergé ailleurs que sur ton DL360), le wildcard ne le concerne
  pas — mais ça veut aussi dire que cette entrée-là ne basculera jamais avec
  ce script. Vérifie ta zone DNS actuelle avant de poser le wildcard pour
  repérer ce genre de cas, surtout sur `trainizer.fr` si des sous-domaines
  pointent vers une autre infrastructure.
- **Le wildcard ne couvre qu'un seul niveau.** `*.domaine.fr` matche
  `truc.domaine.fr` mais pas `truc.staging.domaine.fr`. S'il existe des
  sous-domaines imbriqués à deux niveaux, il faut une entrée wildcard
  séparée pour ce niveau-là (`*.staging.domaine.fr`) ou les lister
  explicitement dans `RECORDS`.

## 5. Vérifier le port-forwarding

Le script teste la joignabilité sur le **port 443** par défaut (modifiable
via `HEALTHCHECK_PORT` dans le workflow). Assure-toi que ce port est bien
redirigé vers ton DL360 **sur la Freebox ET sur la Livebox** — sinon le test
échouera systématiquement côté Orange même quand la ligne fonctionne.

## 6. Tester avant de laisser tourner le cron

Dans l'onglet **Actions** du dépôt GitHub, sélectionne le workflow
`OVH DNS Failover` puis clique sur **Run workflow** pour le lancer
manuellement. Regarde les logs pour vérifier que les deux IP sont bien
testées et que rien ne plante.

Tu peux aussi tester en local avant de pousser sur GitHub :

```bash
pip install ovh
export OVH_ENDPOINT=ovh-eu
export OVH_APPLICATION_KEY=...
export OVH_APPLICATION_SECRET=...
export OVH_CONSUMER_KEY=...
export IP_PRIMARY=...
export IP_SECONDARY=...
export RECORDS="tondomaine.fr:@"
python3 ovh_failover.py
```

## 7. Notifications (optionnel)

Pour être alerté à chaque bascule ou en cas de panne totale, le plus simple
est [ntfy.sh](https://ntfy.sh) (gratuit, sans inscription) :

1. Choisis un nom de "topic" secret, par exemple `failover-a1b2c3`
2. Installe l'app ntfy (iOS/Android) ou abonne-toi sur https://ntfy.sh/failover-a1b2c3
3. Renseigne `WEBHOOK_URL` = `https://ntfy.sh/failover-a1b2c3` dans les secrets GitHub

## 8. Récap quotidien sur Discord (18h)

Le script poste automatiquement un récap de l'état des deux FAI sur un
webhook Discord, une fois par jour à 18h heure de Paris (ajusté
automatiquement à l'heure d'été/hiver, pas besoin d'y retoucher deux fois
par an).

**Créer le webhook Discord :**

1. Dans ton serveur Discord, va sur le salon où tu veux recevoir le récap
2. Paramètres du salon → **Intégrations** → **Webhooks** → **Nouveau webhook**
3. Donne-lui un nom (ex: "FAI Status"), copie l'**URL du webhook**

**Côté GitHub :**

Ajoute un secret `DISCORD_WEBHOOK_URL` avec cette URL. C'est tout — le
workflow existant s'en charge, pas besoin d'un cron séparé. Le récap est
envoyé dans deux cas :

- automatiquement, une fois par jour, sur la fenêtre 18h00-18h04 heure de
  Paris ;
- à chaque déclenchement **manuel** du workflow (bouton *Run workflow* dans
  l'onglet Actions) — pratique pour tester la notification sans attendre
  18h.

En dehors de ces deux cas (les exécutions automatiques toutes les 5 minutes
en dehors de la fenêtre de 18h), aucun message n'est envoyé sur Discord sauf
en cas de bascule ou de panne totale (ça, ça reste géré par `WEBHOOK_URL`,
voir section 7).

Le message contient : l'état de Free, l'état d'Orange, et la cible actuelle
de chaque enregistrement DNS géré. La couleur de l'embed reflète l'état
global : vert (tout va bien), orange (bascule active sur un seul lien),
rouge (les deux liens sont down).

Pour changer l'heure du récap, modifie `DAILY_STATUS_HOUR` dans le fichier
workflow (`18` par défaut).

## Limites à connaître

- **Quota de minutes GitHub Actions.** Sur un dépôt **privé**, le plan gratuit
  inclut 2 000 minutes/mois. Avec une exécution toutes les 5 minutes, ça
  représente environ 8 600 exécutions/mois — largement au-dessus du quota
  gratuit, même si chaque run ne dure que 20-30 secondes (GitHub facture par
  minute entière). Sur un dépôt **public**, les minutes sont illimitées et
  gratuites. Les secrets restent protégés (masqués dans les logs, comme tu
  l'as vu) même sur un dépôt public — c'est la configuration recommandée ici
  pour éviter toute facturation surprise. Si tu préfères vraiment rester en
  privé, passe l'intervalle à 15 minutes (`*/15 * * * *`) pour repasser sous
  le quota gratuit.
- **Fréquence réelle** : GitHub Actions annonce un cron toutes les 5 minutes,
  mais l'exécution peut être retardée de quelques minutes en cas de forte
  charge sur leur infrastructure — ce n'est pas garanti à la seconde près.
- **Propagation côté client** : même une fois le DNS mis à jour côté OVH, le
  temps que le nouveau enregistrement soit visible dépend du cache DNS du
  client (résolveur FAI, box, app). Un TTL bas aide mais ne garantit pas un
  basculement instantané pour tout le monde.
- **Pas de protection anti-flapping avancée** : si une ligne est instable
  (coupures répétées sur quelques minutes), le script peut basculer plusieurs
  fois d'affilée. Si ça devient gênant en pratique, on peut ajouter un
  compteur de stabilité (ex: exiger 3 vérifications saines consécutives avant
  de rebasculer) — dis-le-moi si besoin.