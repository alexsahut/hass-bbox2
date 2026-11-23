<!-- bmad:context -->
<!-- Verified 2026-11-23 against 35aa9b0. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## hass-bbox2

Fork en lecture seule de `cyr-ius/hass-bbox2` : intégration Home Assistant (domaine `bbox`, Python, HACS) pour la Bbox Bouygues F@st 5696b, client API interne sans dépendance. Dépôt public. Règles, choix techniques et maintenance dans `docs/maintenance/`.

## Policy

- N'ajouter aucune écriture vers la box (interrupteur, bouton d'action, requête autre que `GET`) : seul le `POST login` est permis, et une fixture autouse de `tests/conftest.py` fait échouer tout test qui en émet une autre.
- Ne jamais proposer d'activer l'UPnP de la box : l'intégration n'en a pas besoin, le capteur « UPnP IGD activé » le signale comme un problème.
- Ne jamais lire, saisir, stocker ni journaliser le mot de passe d'administration de la box : seul le propriétaire le saisit, dans HA.
- Ne rien installer ni mettre à jour dans Home Assistant sans relecture et sans le go explicite du propriétaire.
- Ne créer ni tag ni release sans le go explicite du propriétaire : un tag `X.Y.Z` déclenche `release.yml`, qui publie `bbox.zip` sur la Marketplace HACS.
- Ne rien ouvrir vers l'amont `cyr-ius/hass-bbox2` (PR, issue, commentaire) ; toujours `gh … --repo alexsahut/hass-bbox2`, base `master`.
- Ne jamais fusionner `upstream/master` : reporter un correctif amont par `git cherry-pick -x` sur une branche `fix/...` (procédure : `docs/maintenance/maintenance.md` §1).
- Ne commiter aucune donnée de la box ni du LAN (IP, MAC, noms d'hôtes, numéro de série) : fixtures anonymisées seulement, selon `tests/fixtures/f5696b/README.md`.

## Where things are

- Client API (GET seulement, erreurs typées) : `custom_components/bbox/api.py` ; endpoints lus avec ou sans mot de passe : `docs/maintenance/maintenance.md` §5.
- Monter la version de HA des tests, versionner ou publier : `docs/maintenance/maintenance.md` §2 et §3.

## Running and verifying

- Lancer les tests par `uv run pytest` (couverture minimale 85 %).
- Linter par `uvx ruff@0.17.5 check .` et `uvx ruff@0.17.5 format --check .`, comme la CI : `uv run ruff` échoue, ruff n'est pas une dépendance du projet.
- Ne pas forcer `homeassistant` par `override-dependencies` : le harnais `pytest-homeassistant-custom-component` épingle HA 2026.10.4 et la collecte échoue sous 2026.11 ; attendre la version du harnais puis `uv lock --upgrade-package pytest-homeassistant-custom-component`.

## Conventions that differ from defaults

- Garder les `unique_id` existants (`{MAC LAN}-{clé}`) : en changer un recrée l'entité et perd son historique.
- Nommer les entités par `translation_key`, en mettant à jour `strings.json`, `translations/en.json` et `translations/fr.json`, jamais par un nom en dur.

## Known pitfalls

- La CI ne teste que la version épinglée de HA : couvrir par un test unitaire la branche de code propre à une autre version de HA (exemple : `DeviceEntry.config_entry_id` depuis 2026.10).

<!-- /bmad:context -->
