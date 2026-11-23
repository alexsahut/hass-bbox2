# Historique du fork (nov. 2026)

Fork de `cyr-ius/hass-bbox2` (1.5.4) pour une Bbox Wi-Fi 7 (Sagemcom F@st 5696b, firmware 25.5.76), maintenu par alexsahut. Objectif : une intégration en **lecture seule**, installable par la Marketplace, testée et maintenable.

## Règles du propriétaire

- Aucune écriture vers la box : interrupteurs (Wi-Fi, invité, WPS, contrôle parental) et boutons (redémarrage) retirés à la source ; le client ne fait que des GET, plus le POST de connexion.
- L'UPnP de la box reste désactivé : l'intégration n'en a pas besoin.
- Le mot de passe d'administration est facultatif et n'est saisi que par le propriétaire dans HA ; aucun outil ni agent ne le manipule.
- Rien n'est installé dans HA sans relecture et sans go du propriétaire.

## Choix techniques

- Connexion par `mabbox.bytel.fr` : par adresse IP, toute l'API redirige (302) et la connexion cassait ; certificat vérifié.
- Client interne GET-only (MIT) ; `bboxpy` n'est plus une dépendance depuis S4 (le fork bboxpy n'est plus maintenu ; son archivage a été décidé le 23/11/2026).
- Tolérance par endpoint (une erreur n'invalide pas tout) ; reconnexion unique sur 401, puis réauthentification HA.
- Identifiant stable = MAC LAN publique de la box, identique avec ou sans mot de passe ; le n° de série n'est qu'une information.
- Noms d'entités 100 % traduits (`translation_key`).
- Tests : harnais `pytest-homeassistant-custom-component` bloqué à HA 2026.10.4 (pas encore publié pour 2026.11) ; vérification réelle sous 2026.11 faite à l'installation.

## Stories

| Story | PR | Contenu |
|---|---|---|
| Analyse | #1 | Compatibilité F@st 5696b : 37 endpoints lus en GET sans auth (19 en 200, 13 en 401, 5 en 404) ; rapport masqué [`analyse-compat-f5696b.md`](analyse-compat-f5696b.md) |
| S1 | #2 | Socle du fork, note de maintenance, retrait de l'auto-merge dependabot |
| S2 | #4 | Retrait de toutes les écritures et nettoyage des entités orphelines |
| S4 | #5 | Client interne GET-only, mot de passe facultatif et masqué, reconnexion, diagnostics expurgés, retrait de bboxpy |
| S3 | #6 | Corrections des capteurs (« Dernier redémarrage », occupation en %, lien WAN, ports d'après la box) |
| S6 | #7 | Capteurs publics ; identifiant stable = MAC LAN |
| S8 | #8 | Version 2.0.0, CHANGELOG, README, procédure [`installation-test.md`](installation-test.md), étape « Reconfigurer » |
| S9 | #9 | Finitions avant release : noms français, suivi des appareils désactivé par défaut, doc UPnP sans objet |
| — | #10 | 2.0.1 : précision d'affichage |
| S11 | #11 | 2.0.2 : noms lisibles des appareils, choix des appareils suivis, nettoyage sans supprimer un appareil partagé avec une autre intégration |
| S12 | #12 | 2.0.3 : décodage des textes encodés deux fois, traceurs actifs dès le premier setup et rattachés à l'appareil de l'hôte, suppression d'un appareil d'hôte = retrait du suivi |
| S13 | #16 | Garde de lecture seule (`tests/test_read_only.py`) : plateformes admises, bouton Refresh seul, aucune entité d'action ni service du domaine `bbox` |

## Releases

2.0.0, 2.0.1, 2.0.2 et 2.0.3 publiées le 22/11/2026, chacune après go du propriétaire ; 2.0.3 en service depuis le 22/11/2026. 233 tests, couverture 99,46 %, CI à 4 contrôles.

## Pistes ouvertes

- S7 éventuel : Wi-Fi 6 GHz et MLO (Wi-Fi 7), à partir des diagnostics expurgés.
- Rebasculer les tests sur HA 2026.11 dès que le harnais est publié.
