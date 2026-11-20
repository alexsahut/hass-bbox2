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

- Versions `MAJOR.MINOR.PATCH` dans `manifest.json` ; suffixe `-dev` (ex. `2.1.0-dev`) pendant le développement. Première version du fork : `2.0.0` (MAJOR : entités supprimées et `unique_id` changés par rapport à l'amont 1.5.4). Chaque version est décrite dans `CHANGELOG.md`.
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
| Sans mot de passe (publics) | `device`, `device/cpu`, `device/mem`, `device/led`, `wan/ip`, `wan/ip/stats`, `summary`, `wireless/wps`, `upnp/igd`, `wan/ftth/stats`, `wan/diags`, `lan/stats`, `alerts` (S6), `lan/ip` (identifiant) |
| Avec mot de passe (en plus) | `hosts`, `wireless`, `speedtest/info`, `device/summary` |

`parentalcontrol` n'est plus lu. En plus, le config flow lit `lan/ip` (public, adresse MAC LAN) ; les diagnostics lisent quelques endpoints supplémentaires, toujours en `GET` (`lan/stats` et `wan/ftth/stats` n'en font plus partie depuis S6 : le coordinateur les lit déjà).

**Sans mot de passe**, les entités qui dépendent d'un endpoint authentifié ne sont pas créées (Speedtest download, device trackers) et celles déjà enregistrées sont retirées du registre.

**Reconnexion** : avec un mot de passe, le client ouvre une session avant la première requête (un seul login pour les requêtes concurrentes) et envoie le cookie de session, plus le jeton `device/token` s'il est lisible. Sur `401`, il se reconnecte puis refait **une seule** tentative. Si le login est refusé, le coordinateur lève `ConfigEntryAuthFailed` (flux de ré-authentification, où le mot de passe est aussi facultatif). Un second `401` après reconnexion n'est qu'une erreur de l'endpoint.

**Tolérance par endpoint** : le coordinateur lit chaque endpoint indépendamment. Un endpoint en erreur (404, timeout, JSON invalide…) ne rend indisponibles que les entités qui en dépendent ; l'erreur est journalisée une fois, puis la reprise. Un `404` est définitif : l'endpoint n'est plus demandé (modèle sans cette fonction). `UpdateFailed` seulement si aucun endpoint n'a répondu.

**Identifiant de la box** : adresse MAC LAN (`lan/ip` → `lan.ip.mac`, public), normalisée par `format_mac`, avec ou sans mot de passe. Elle sert de `unique_id` à l'entrée, d'identifiant à l'appareil Bbox, et de préfixe aux `unique_id` des entités (`{MAC}-{clé}`) et des device trackers. Le numéro de série n'est qu'une information de l'appareil (`serial_number`, lu dans `device` avec mot de passe). Ré-authentification : l'identifiant ne change pas ; une MAC différente de celle de l'entrée donne `wrong_account`. Pas de conversion depuis l'identifiant amont (numéro de série ou `ABC12345`) : aucune instance n'était installée (incompatibilité notée dans `CHANGELOG.md`).

## 7. Capteurs (S3)

| Entité | Source | Classe | Unité | `state_class` | Activée par défaut | `unique_id` (après la MAC LAN) |
|---|---|---|---|---|---|---|
| System Temperature | `device` / `device/cpu` | temperature | °C | measurement | oui | `info.device.temperature.current` |
| Downloaded / Uploaded | `wan/ip/stats` | data_size | kB | total_increasing | oui | `wan_ip_stats.wan.ip.stats.{rx,tx}.bytes` |
| Download / Upload speed | `wan/ip/stats` | data_rate | kb/s | measurement | oui | `…{rx,tx}.bandwidth` |
| Download / Upload bandwidth occupation | `wan/ip/stats` | aucune | % | measurement | oui | `…{rx,tx}.occupation` (conservé) |
| Download / Upload occupation (raw) | `wan/ip/stats` | aucune | aucune | measurement | **non** | `…{rx,tx}.occupation_raw` (nouveau) |
| Download / Upload discard packet, error packet | `wan/ip/stats` | aucune | aucune | total_increasing | **non** | `…{rx,tx}.{packetsdiscards,packetserrors}` |
| IP Address, IPv6 Address | `wan/ip` | aucune | aucune | aucun | oui | `wan_ip.wan.ip.address`, `…ip6address.0.ipaddress` |
| Boot counter | `device` | aucune | aucune | aucun | oui | `info.device.numberofboots` |
| Last boot | `device` | timestamp | — | aucun | oui | `info.device.boot_time` (remplace `info.device.uptime`) |
| Memory free | `device/mem` | aucune | % | measurement | oui | `memory.device.mem.free` |
| Speedtest download | `speedtest/info` (mot de passe) | data_rate | kb/s | measurement | **non** | `speedtest_infos.…download.0.speed` |
| Link status (binary) | `wan/ip` | connectivity | — | — | oui | `info.device.status` (conservé) |
| Ethernet port N (binary) | `device/led` | aucune | — | — | **non** | `led.ethernetPort.{position}.state` |

**Dernier démarrage** : `device.now` − `device.uptime`, tronqué à la seconde. `now` et `uptime` sont lus au même instant par la box mais arrondis séparément : la valeur oscille d'une ou deux secondes. Le capteur garde donc la valeur précédente tant que le nouvel horodatage en diffère de moins de 10 s, ce qui évite d'écrire un état à chaque cycle ; un vrai redémarrage (écart ≫ 10 s) met la valeur à jour. L'ancien capteur « Uptime » (`info.device.uptime`) est supprimé du registre au démarrage (son historique n'est pas migré).

**Link status** : `ON` si `wan.link.state` de `wan/ip` vaut `Up` (état du lien physique/optique). `wan.internet.state` n'est pas utilisé : c'est un entier dont la signification n'est pas documentée (valeur `2` sur une box connectée). Le `device.status` (état de la box) n'est plus utilisé. Le `unique_id` est conservé.

**Ports Ethernet** : un binary_sensor par entrée de `ethernetPort` (`device/led`), nommé d'après son `id` réel (« Ethernet port 3 »). La clé d'unicité reste `led.ethernetPort.{position}.state`, identique à l'ancienne pour les ports existants (la 5696b renvoie les `id` 1 à 5 dans l'ordre) ; l'état est cherché par `id`. Les ports apparaissent dès que `device/led` répond, même après le démarrage. Un port disparu de la réponse passe à l'état inconnu.

### Capteurs publics (S6)

Tous lisibles sans mot de passe (`unique_id` = `{MAC LAN}-{clé}`). Les noms viennent des `translation_key` (`strings.json`, `translations/en.json`, `translations/fr.json`).

| Entité | Plateforme | Source (clé = chemin dans les données) | Classe | Unité | `state_class` | Activée par défaut | Accès |
|---|---|---|---|---|---|---|---|
| Wi-Fi activé | binary_sensor | `summary` → `wireless.radio` (`summary.wireless.radio`) | aucune | — | — | oui | public |
| Wi-Fi invité activé | binary_sensor | `summary.wireless.guestenable` | aucune | — | — | oui | public |
| Wi-Fi invité 2,4 GHz / 5 GHz | binary_sensor | `summary.wireless.guest24enable` / `guest5enable` | aucune | — | — | **non** | public |
| SSID de compatibilité 2,4 GHz / 5 GHz | binary_sensor | `summary.wireless.compatibility24enable` / `compatibility5enable` | aucune | — | — | **non** | public |
| WPS activé | binary_sensor | `wireless/wps` → `wps.wps.enable` | aucune | — | — | oui | public |
| UPnP IGD activé | binary_sensor | `upnp/igd` → `upnp_igd.upnp.igd.enable` | problem | — | — | oui | public |
| Lien FTTH | binary_sensor | `wan/ftth/stats` → `wan_ftth_stats.wan.ftth.state` (`Up`) | connectivity | — | — | oui | public |
| IPv6 opérationnel | binary_sensor | `wan/ip` → `wan_ip.wan.ip.ip6state` + `ip6address` | aucune | — | — | oui | public |
| Type de lien | sensor | `wan/ftth/stats` → `wan_ftth_stats.wan.ftth.mode` | aucune (catégorie diagnostic) | — | — | oui | public |
| Débit contractuel descendant / montant | sensor | `wan/ip/stats` → `…{rx,tx}.contractualBandwidth` | data_rate | kb/s | aucun | oui | public |
| Alertes | sensor | `alerts` → `alerts.alerts.list` (longueur) | aucune | — | measurement | oui | public |
| Appareils connus | sensor | `summary` → `summary.hosts` (longueur) | aucune | — | measurement | oui | public |
| Latence ping | sensor | `wan/diags` → `wan_diags.diags.ping` | duration | ms | measurement | oui | public |
| Latence DNS / HTTP | sensor | `wan_diags.diags.dns` / `http` | duration | ms | measurement | **non** | public |
| Trafic LAN reçu / émis | sensor | `lan/stats` → `lan_stats.lan.stats.{rx,tx}.bytes` (chaînes) | data_size | octets (affichage Go) | total_increasing | **non** | public |

Règles :
- **UPnP IGD** : sentinelle de sécurité. `PROBLEM` : « activé » s'affiche comme un problème (icône/état d'alerte), « désactivé » = normal. Pas de repli sur `summary.services.upnp.igd.enable` : si `upnp/igd` est absent, seule cette entité est indisponible.
- **IPv6 opérationnel** : `on` si `wan.ip.ip6state` vaut `Up` **et** qu'au moins une adresse de `wan.ip.ip6address` est en `Preferred` (adresse valide, utilisable comme source). `ip6state` absent : inconnu ; `Up` sans adresse `Preferred` : `off`.
- **Type de lien** : valeur brute de `wan.ftth.mode` (ex. `1000baseT-HD`, mode négocié du port optique), sans traduction. `summary.link.type` (`bosa`) n'est pas utilisé (même valeur dans `wan/ip.link.type`).
- **Alertes** : longueur de `alerts.list` (`alerts`) ; à défaut (endpoint absent), `summary.alerts.count` s'il est entier. Sinon inconnu.
- **Appareils connus** : nombre d'éléments de `summary.hosts` ; ni nom ni adresse n'est exposé (pas d'attribut). Ce n'est pas le nombre d'appareils *actifs*.
- **Latences** : le « dernier point » est le **dernier élément** de la liste de la série (`ping`, `dns`, `http`) dans l'ordre renvoyé par la box (chronologique : les points vides sont en tête), quel que soit le protocole (la box alterne IPv4/IPv6, d'où un léger va-et-vient de la valeur). On prend `average`. Si ce point n'a pas de mesure (`tries` ou `success` à 0, `average` absent ou négatif), la série est vide ou le point invalide : état **inconnu**, jamais 0 ms. Unité : la box donne des valeurs de l'ordre de 6 000 à 25 000 ; elles sont lues comme des **microsecondes** (hypothèse non vérifiée : ping ≈ 7 ms, HTTP ≈ 23 ms), divisées par 1000.
- **Trafic LAN** : les compteurs sont des chaînes d'entiers, convertis en `int` ; unité native octet, affichée en Go (unité suggérée à la création de l'entité). `rx`/`tx` sont du point de vue de la box. Le compteur peut repartir de zéro au redémarrage.
- **Mode sans mot de passe** : ces entités sont les seules créées ; `hosts`, `wireless`, `speedtest/info` et `device/summary` ne sont pas lus, ni les device trackers ni le Speedtest créés (tests : `tests/test_public_sensors.py`, `tests/test_setup.py`). L'aide du config flow, du flux d'options et le message de ré-authentification indiquent ce que le mot de passe débloque.

**À surveiller (relecture S3)** : le `unique_id` des ports Ethernet est bâti sur la **position** dans `ethernetPort` (`led.ethernetPort.{position}.state`) alors que l'état est cherché par l'`id`. Si la box réordonnait la liste, un port pourrait changer de nom (« Ethernet port N ») sans changer d'`unique_id` : accepté, à surveiller.

### Occupation de la bande passante : incertitudes

Fixture `wan_ip_stats.json` (rx / tx) : `occupation` = 25 / 2, `bandwidth` = 25525 / 2560, `maxBandwidth` = 1 000 000, `contractualBandwidth` = 8 000 000 / 1 000 000.

- **Unité de `bandwidth`** : supposée en kb/s (comme avant ; 25 525 kb/s ≈ 25,5 Mb/s). Cohérent avec `maxBandwidth` = 1 000 000 kb/s = 1 Gb/s (plafond du port) et `contractualBandwidth` = 8 000 000 / 1 000 000 kb/s (8 Gb/s descendant, 1 Gb/s montant), qui correspond à une offre FTTH multi-gigabit. Non vérifié avec l'interface web de la box.
- **Unité de `occupation`** : indéterminée. 25 est compatible avec deux lectures : ‰ de `maxBandwidth` (25525 / 1 000 000 = 25,5 ‰ → 25) ou Mb/s (25,5 Mb/s → 25) ; de même pour la voie montante (2,56 → 2). Ce n'est **pas** un pourcentage de `maxBandwidth` (2,55 %). La valeur est tronquée à l'entier. Le champ brut est exposé tel quel, sans unité, dans un capteur désactivé par défaut.
- **Capteur en %** : `bandwidth × 100 / contractualBandwidth`, borné à 0–100, arrondi à 0,01 ; inconnu si `contractualBandwidth` est absent, nul ou non numérique. Il remplace l'ancien calcul sur `maxBandwidth`, qui plafonne à 1 Gb/s alors que l'offre descendante est plus rapide. Il reste dépendant de l'hypothèse sur l'unité de `bandwidth`.

## 8. Surcharge de l'intégration native de HA core

Cette intégration personnalisée, de domaine `bbox`, **surcharge** l'intégration native `bbox` de Home Assistant core (voir §4). Au démarrage, HA journalise l'avertissement attendu « We found a custom integration bbox which has not been tested by Home Assistant » / « custom integration overrides core integration » : ce n'est pas une erreur.
