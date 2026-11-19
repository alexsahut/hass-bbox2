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

À surveiller : corrections de `coordinator.py`, `config_flow.py` et du client (`bboxpy` côté amont, remplacé ici par `api.py`), changements d'API HA, nouveaux firmwares Bbox.
À ignorer : tout ce qui ajoute des écritures sur la box (switch, button reboot/ring, etc.), qui sont supprimées dans ce fork (S2). L'intégration est en lecture seule ; seul le bouton Refresh subsiste, et il ne fait qu'interroger la box.

Reporter un correctif : ne jamais fusionner `upstream/master` en bloc. Créer une branche `fix/...` depuis `master`, puis `git cherry-pick -x <sha>` des seuls commits utiles (le `-x` garde la trace de l'origine), résoudre les conflits, lancer les tests, ouvrir une PR vers `master` du fork et la relire avant fusion. Aucune PR n'est fusionnée automatiquement.

## 2. Vérification à chaque version mensuelle de HA

1. Lire les « breaking changes » de la version (config entries, coordinator, entity, device tracker).
2. Mettre à jour la version de HA pour les tests : `pytest-homeassistant-custom-component` épingle `homeassistant` exactement, donc attendre la release du plugin ciblant la nouvelle version, puis `uv lock --upgrade-package pytest-homeassistant-custom-component && uv sync`. Ne pas forcer `homeassistant` par un `override-dependencies` : avec HA 2026.11.1 et le plugin 0.13.375 (HA 2026.10.4), la collecte des tests échoue (`RuntimeError: httpx was already imported; call alias_httpx() ...`, HA 2026.11 remplaçant `httpx` par `httpx2`). Tant que le plugin n'est pas publié pour la version courante de HA, les tests tournent sur la version précédente : le noter dans la PR et garder l'issue de suivi ouverte.
3. Lancer `uv run pytest` (le seuil de couverture est de 85 %) et `uv run ruff check . && uv run ruff format --check .`.
4. Chercher les avertissements de dépréciation : `uv run pytest -W error::DeprecationWarning` (informatif).
5. Vérifier que la CI (tests, lint, validate hassfest + HACS) est verte, puis tester sur une vraie installation HA avant de publier.

## 3. Politique de version

- Versions `MAJOR.MINOR.PATCH` dans `manifest.json`, `1.6.0-dev` pendant le développement.
- PATCH : correctif ou compatibilité HA ; MINOR : nouvelle entité ou nouveau capteur ; MAJOR : changement incompatible (entités supprimées, domaine, etc.).
- Publication : mettre à jour `version` dans `manifest.json`, fusionner, puis créer le tag `X.Y.Z` ; `release.yml` crée la release GitHub avec `bbox.zip`. `hacs.json` déclare `"zip_release": true` et `"filename": "bbox.zip"` : la Marketplace installe exactement cette archive (le code publié est celui du tag), et ne propose que les versions publiées en release, jamais l'état courant de `master`.
- `hacs.json` : version minimale de HA relevée seulement quand le code l'exige.

## 4. Surcharge de l'intégration native `bbox` de HA

Home Assistant contient une intégration native nommée `bbox` (configuration YAML, bibliothèque `pybbox`). Ce fork garde le domaine `bbox`, comme l'amont : une fois installé dans `custom_components/bbox`, il **remplace** l'intégration native. Au démarrage, HA journalise donc un avertissement du type « We found a custom integration bbox which has not been tested by Home Assistant… » et signale que l'intégration personnalisée surcharge celle du cœur : c'est attendu.

Conséquences :
- ne pas configurer l'intégration native `bbox` en YAML en parallèle : elle serait ignorée ;
- si HA supprime ou renomme un jour son intégration native, vérifier que rien ne change pour ce fork ;
- en cas de doute sur la version chargée, la page de l'intégration indique « Intégration personnalisée » et la version du `manifest.json`.

## 5. Client API interne (S4)

`bboxpy` (GPL) n'est plus utilisé : `manifest.json` n'a plus aucune dépendance (`requirements: []`). Le client est `custom_components/bbox/api.py`, écrit pour ce fork (MIT), en **lecture seule**.

- **Requêtes** : uniquement `GET`. Seule exception, le `POST login` quand un mot de passe est configuré. `BboxClient._request` refuse tout autre couple méthode/endpoint (`ValueError`), et le client n'a aucune méthode publique d'écriture. Les tests le vérifient, et chaque test échoue si une requête autre que `GET` (ou le `POST login`) est émise.
- **Session** : session aiohttp fournie par HA (`async_get_clientsession(hass, verify_ssl=...)`), rien à créer ni à fermer. TLS vérifié par défaut (option `verify_ssl` conservée, désactivée automatiquement si l'hôte saisi est une adresse IP). Pas de `verify_ssl=` dans les appels aiohttp. Les redirections ne sont **pas suivies** (`allow_redirects=False`).
- **Hôte** : `mabbox.bytel.fr` par défaut, HTTPS, base `/api/v1/`. Par IP, la box répond `302` vers `mabbox.bytel.fr` : le config flow affiche l'erreur « redirect » (utiliser `mabbox.bytel.fr`). Un nom non résolu donne l'erreur « dns_error ».
- **Erreurs typées** : `BboxConnectionError`, `BboxDnsError`, `BboxRedirectError`, `BboxAuthError` (`BboxLoginError` pour un login refusé), `BboxNotFoundError` (404), `BboxResponseError` (réponse invalide).

Endpoints lus à chaque cycle :

| Mode | Endpoints (`/api/v1/…`) |
|---|---|
| Sans mot de passe (publics) | `device`, `device/cpu`, `device/mem`, `device/led`, `wan/ip`, `wan/ip/stats`, `summary`, `wireless/wps` |
| Avec mot de passe (en plus) | `hosts`, `wireless`, `speedtest/info`, `device/summary` |

`parentalcontrol` n'est plus lu. En plus, le config flow lit `lan/ip` (public, adresse MAC LAN) et, avec mot de passe, `device/summary` (numéro de série) ; les diagnostics lisent quelques endpoints supplémentaires, toujours en `GET`.

**Sans mot de passe**, les entités qui dépendent d'un endpoint authentifié ne sont pas créées (Speedtest download, device trackers) et celles déjà enregistrées sont retirées du registre.

**Reconnexion** : avec un mot de passe, le client ouvre une session avant la première requête (un seul login pour les requêtes concurrentes) et envoie le cookie de session, plus le jeton `device/token` s'il est lisible. Sur `401`, il se reconnecte puis refait **une seule** tentative. Si le login est refusé, le coordinateur lève `ConfigEntryAuthFailed` (flux de ré-authentification, où le mot de passe est aussi facultatif). Un second `401` après reconnexion n'est qu'une erreur de l'endpoint.

**Tolérance par endpoint** : le coordinateur lit chaque endpoint indépendamment. Un endpoint en erreur (404, timeout, JSON invalide…) ne rend indisponibles que les entités qui en dépendent ; l'erreur est journalisée une fois, puis la reprise. Un `404` est définitif : l'endpoint n'est plus demandé (modèle sans cette fonction). `UpdateFailed` seulement si aucun endpoint n'a répondu.

**Identifiant de la box** : avec mot de passe, `unique_id` de l'entrée = numéro de série (`device/summary`) ; sans mot de passe, adresse MAC LAN (`lan/ip`, public). Les `unique_id` des entités ne changent pas dans cette story (`{numéro de série}-{clé}`, ou `ABC12345-{clé}` si `device` ne donne pas le numéro de série, ce qui est le cas sans mot de passe) : leur refonte est l'objet de S5.

## 6. Surcharge de l'intégration native de HA core

Cette intégration personnalisée, de domaine `bbox`, **surcharge** l'intégration native `bbox` de Home Assistant core (voir §4). Au démarrage, HA journalise l'avertissement attendu « We found a custom integration bbox which has not been tested by Home Assistant » / « custom integration overrides core integration » : ce n'est pas une erreur.
