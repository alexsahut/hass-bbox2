# Note de maintenance du fork

Fork : `alexsahut/hass-bbox2` (branche par défaut `master`), amont : `cyr-ius/hass-bbox2`.
Ce fork est en lecture seule et indépendant : on ne contribue rien à l'amont (ni issue, ni PR, ni commentaire).

## 1. Suivi de l'amont

Ajouter le remote une fois : `git remote add upstream https://github.com/cyr-ius/hass-bbox2.git`.

Environ une fois par mois, ou quand une version de HA sort :

```bash
git fetch upstream
git log --oneline master..upstream/master          # nouveautés amont
git diff master...upstream/master -- custom_components/bbox/
```

À surveiller : corrections de `coordinator.py`, `config_flow.py` et du client (`bboxpy`, version dans `manifest.json`), changements d'API HA, nouveaux firmwares Bbox.
À ignorer : tout ce qui ajoute des écritures sur la box (switch, button reboot/ring, etc.), qui sont supprimées dans ce fork.

Reporter un correctif : ne jamais fusionner `upstream/master` en bloc. Créer une branche `fix/...` depuis `master`, puis `git cherry-pick -x <sha>` des seuls commits utiles (le `-x` garde la trace de l'origine), résoudre les conflits, lancer les tests, ouvrir une PR vers `master` du fork et la relire avant fusion. Aucune PR n'est fusionnée automatiquement.

## 2. Vérification à chaque version mensuelle de HA

1. Lire les « breaking changes » de la version (config entries, coordinator, entity, device tracker).
2. Mettre à jour la version de HA pour les tests : `pytest-homeassistant-custom-component` épingle `homeassistant` exactement, donc attendre la release du plugin ciblant la nouvelle version, puis `uv lock --upgrade-package pytest-homeassistant-custom-component && uv sync`.
3. Lancer `uv run pytest` (le seuil de couverture est de 85 %) et `uv run ruff check . && uv run ruff format --check .`.
4. Chercher les avertissements de dépréciation : `uv run pytest -W error::DeprecationWarning` (informatif).
5. Vérifier que la CI (tests, lint, validate hassfest + HACS) est verte, puis tester sur une vraie installation HA avant de publier.

## 3. Politique de version

- Versions `MAJOR.MINOR.PATCH` dans `manifest.json`, `1.6.0-dev` pendant le développement.
- PATCH : correctif ou compatibilité HA ; MINOR : nouvelle entité ou nouveau capteur ; MAJOR : changement incompatible (entités supprimées, domaine, etc.).
- Publication : mettre à jour `version` dans `manifest.json`, fusionner, puis créer le tag `X.Y.Z` ; `release.yml` crée la release GitHub avec `bbox.zip`.
- `hacs.json` : version minimale de HA relevée seulement quand le code l'exige.
