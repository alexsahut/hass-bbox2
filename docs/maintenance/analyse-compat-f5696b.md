# Analyse de compatibilité : hass-bbox2 / bboxpy ↔ Bbox Wi-Fi 7 (Sagemcom F@st 5696b)

- **Date** : 2026-11-19
- **Périmètre** : étape 1, analyse seule (aucun code modifié, rien installé dans Home Assistant, aucune configuration de la box modifiée).
- **Code analysé** : `hass-bbox2` 1.5.4 (branche `master` = `upstream/master`, aucun changement de code depuis le tag) ; `bboxpy` 1.4.1 (version figée par `manifest.json`, aucun changement de code entre le tag et `master`).
- **Cible** : Sagemcom F@st 5696b (`modelname` = `F@st5696b`, `modelclass` = `F5696b`), firmware `25.5.76`, accès FTTH (`link.type` = `bosa`), Home Assistant 2026.11.1 installé depuis la Marketplace.
- **Méthode de sondage** : requêtes HTTP `GET` uniquement, sans cookie, sans en-tête d'authentification, sans identifiant, espacées de 1,5 s. Les réponses brutes sont stockées hors dépôt. Ce document ne contient que la structure des réponses : clés, types, codes HTTP. Les valeurs sensibles (IP, MAC, numéro de série, noms d'appareils, règles NAT, préfixes IPv6) sont omises.

---

## 1. Résumé exécutif

**Ce qui marche (vérifié sans authentification)**
- Tous les champs lus par les capteurs « système » et « WAN » existent sur le firmware 25.5.76, avec les types attendus : `device`, `device/cpu`, `device/mem`, `device/led`, `wan/ip`, `wan/ip/stats`. Le repli de température sur `cpu.temperature.main` (en m°C) fonctionne : `device.temperature` est absent.
- L'intégration n'a **aucune dépendance à UPnP** : pas de découverte SSDP (`"ssdp": []`) et aucun appel à `upnp/*`. L'état UPnP IGD lu sur la box est bien `enable = 0`, conformément à l'exigence.
- 17 tests sur 17 passent sous HA 2026.10.4 (CI amont du 2026-11-16).

**Ce qui casse ou risque fortement de casser**
1. **Configuration par IP** : sur ce firmware, **chaque URL `/api/v1/*` appelée par IP renvoie un 302** vers `https://mabbox.bytel.fr:443/api/v1/...`. Sur un 302, aiohttp convertit le `POST /login` en `GET` et supprime le corps. La connexion par IP, documentée dans le README, a donc de fortes chances d'échouer. Il faut utiliser l'hôte `mabbox.bytel.fr`, ce qui suppose que le DNS vu par HA résolve ce nom vers l'IP LAN de la box en **IPv4** : bboxpy force `AF_INET`.
2. **Aucune reconnexion** : `bboxpy` ne remet jamais `_authenticated` à `False`. Quand la session de la box expire, les appels échouent en 401 jusqu'au rechargement de l'intégration. `ConfigEntryAuthFailed` n'est jamais levé : le seul `raise` se trouve dans `_async_setup`, où rien ne s'authentifie.
3. **Fragilité du coordinateur** : `_call()` renvoie `{}` en cas d'erreur, puis `check_list({})` lève `UpdateFailed`, et `merge_objects({})` déclenche une `AssertionError`. **Un seul endpoint en erreur rend donc toute l'intégration indisponible.**
4. **Wi-Fi 7 non modélisé** : bboxpy ne connaît que les bandes `24` et `5`, plus `guest`. Sur la 5696b, le résumé public n'expose que des clés 2,4 / 5 GHz et un SSID « compatibility ». Aucune clé 6 GHz ni MLO n'est visible sans authentification. Le switch « Wifi (all) » ne lit que `radio.24.enable`.
5. **CI amont rouge** : couverture de 79 % pour un seuil de 85 %, et validation Marketplace en échec faute d'assets de marque (`brand/icon.png`).

**Non vérifiable à cette étape** (endpoints en 401, l'authentification étant interdite) : `hosts` (device trackers), `wireless` (switchs Wi-Fi), `parentalcontrol`, `speedtest/info`, `device/summary` (numéro de série utilisé dans le config flow). Le schéma de `hosts/me`, qui est public, laisse penser que `hosts` reste compatible.

### Verdict par plateforme HA

| Plateforme | Verdict 5696b / 25.5.76 | Commentaire |
|---|---|---|
| `sensor` (17 entités) | 🟢 Compatible (schéma vérifié) | Sauf « Speedtest download » (401, non vérifié). Calcul d'« occupation » discutable (§3.4). Bug `state_class` sur Uptime. |
| `binary_sensor` (6) | 🟢 Compatible | `device.status` = int, `led.ethernetPort[].state` = `Up`/`Down`. Le nombre de ports est à confirmer (§3.5). |
| `device_tracker` (N, désactivés par défaut) | 🟡 Probable, non prouvé | `hosts` exige une authentification. `hosts/me` montre les champs utilisés (`macaddress`, `ipaddress`, `active`, `link`, `hostname`). |
| `switch` (6 + N) | 🔴 À supprimer (écriture) | Ils sont de toute façon aveugles au 6 GHz / MLO. |
| `button` (2) | 🔴 Restart à supprimer / 🟢 Refresh à garder | Refresh ne fait qu'un rafraîchissement local du coordinateur. |
| `config_flow` | 🟠 À risque | Mot de passe obligatoire, redirection 302 si l'hôte est une IP, numéro de série via `device/summary` (401). |
| `diagnostics` | 🟢 Tolérant | Chaque appel est encapsulé (`suppress`). `voip/voicemail` répond 404 sur cette box. |

---

## 2. Endpoints : code vs firmware réel

### 2.1 Comportement transport observé

- `GET https://<IP_LAN>/api/v1/<endpoint>` donne **302** pour les 37 endpoints testés, `Location: https://mabbox.bytel.fr:443/api/v1/<endpoint>` et `Server: Lighttpd`. La redirection conserve le chemin. Le comportement des paramètres de requête, comme `?btoken=…`, n'a pas été observé.
- `mabbox.bytel.fr` résout localement (résolveur du poste de sondage) vers l'IP LAN de la box en IPv4 et vers une IPv6 globale de la box.
- Le sondage a donc été fait en **deux passes** : une première par IP (302 partout), puis un GET par endpoint sur `https://mabbox.bytel.fr`, épinglé sur l'IP LAN (`curl --resolve`). Cela fait deux GET par endpoint au lieu d'un : la première réponse n'était qu'une redirection, sans contenu. Aucune autre requête n'a été faite.
- Les erreurs suivent le format habituel des Bbox : `{"exception":{"domain":"v1/<ep>","code":"401","errors":[{"name":"","reason":"Operation requires authentication"}]}}`, et `"domain":"unknown","code":"404","reason":"Operation not found"` pour les 404.
- Le certificat TLS n'a pas été validé : le sondage utilisait `-k`. Il faut vérifier que `mabbox.bytel.fr` présente un certificat valide, car la valeur par défaut de l'intégration est `verify_ssl = True`.

### 2.2 Tableau endpoint par endpoint

Légende des usages HA : **coord** = coordinateur, interrogé à chaque cycle (60 s par défaut) ; **diag** = diagnostics uniquement ; **—** = non utilisé par l'intégration.
Code HTTP = réponse sans authentification via `mabbox.bytel.fr`. Par IP, tous les endpoints répondent 302.

| Endpoint (`/api/v1/…`) | Méthode bboxpy | Usage HA | HTTP sans auth | Auth requise | Écarts de schéma vs code |
|---|---|---|---|---|---|
| `device` | `device.async_get_bbox_info` | coord → Temperature (1er essai), Boot counter, Uptime, Link status, registre d'appareils, `unique_id` | **200** | Non (vue partielle ?) | ⚠️ `serialnumber` **absent** sans auth. `temperature` absent (le repli CPU prend le relais). `hwRevision` absent (inutilisé). Nouveaux champs : `lastFactoryReset`, `newihm`, `newihmCdc`. `main.version` = firmware ✔ |
| `device/cpu` | `async_get_bbox_cpu` | coord (optionnel) → Temperature (repli) | **200** | Non | ✔ `device.cpu.temperature.main` (int, m°C). `cpu.time.idle` est une **str** (les autres compteurs sont des int) : inutilisé aujourd'hui. |
| `device/mem` | `async_get_bbox_mem` | coord → Memory free | **200** | Non | ✔ `device.mem.{total,free,cached,committedas}` int |
| `device/led` | `async_get_bbox_led` | coord → Ethernet port 1-5 | **200** | Non | ✔ `ethernetPort[5]{id,state}`, `state` ∈ `Up`/`Down`. Bloc supplémentaire `screen{state,counter}`. |
| `device/summary` | `async_get_bbox_summary` | config_flow, reauth (numéro de série), diag | **401** | Oui | Non vérifiable |
| `device/token` | `auth.async_get_token` | Avant **chaque** requête | non sondé (interdit) | Oui | — |
| `login` (POST) | `auth.async_auth` | Avant le 1er appel | non sondé (interdit) | — | Redirection 302 probable par IP (§3.1) |
| `logout` (POST) | `async_logout` | — | non sondé | — | — |
| `device/log` | `async_get_bbox_log` | — | **401** | Oui | — |
| `summary` | `Bbox.async_get_summary` | — | **200** | Non | Riche et public : `internet.state`, `link{state,type}`, `wireless{status,radio,guestenable,guest24enable,guest5enable,compatibility24enable,compatibility5enable,wps{24,5,…}}`, `hosts[]{hostname,ipaddress}`, `alerts.count`, `cpl.count`, `wan.ip.state`, `services.*`, `authenticated` (int). Aucune clé 6 GHz. |
| `dyndns` | `ddns.async_get_ddns` | diag | **401** | Oui | — |
| `dyndns/{id}` | `async_get_ddns_by_id` | — | non sondé (paramétré) | — | — |
| `iptv` | `iptv.async_get_iptv_info` | diag | **401** | Oui | — |
| `hosts` | `lan.async_get_connected_devices` | coord → device_tracker, switchs de contrôle parental par appareil | **401** | Oui | Non vérifiable. Voir `hosts/me` pour le schéma probable. |
| `hosts/me` | `async_get_device_infos` | diag | **200** | Non | `host{id,hostname,macaddress,ipaddress,type,link,devicetype,ip6address[],ethernet{},wireless{band,rssi0,mcs,rate,estimatedRate,…},`**`wirelessByBand[]`**`,plc{},informations{},parentalcontrol{enable,…},lease,firstSeen,lastSeen,active,scan{},ping{}}` + `wirelesshosts[]` + `extenderhosts[]`. `userfriendlyname` **absent** (le code se replie sur `hostname` ✔). `wirelessByBand` est vraisemblablement la structure MLO / multibande. |
| `lan/ip` | `async_get_ip_infos` | — | **200** | Non | `lan.ip{…, mac, hostname, domain}`, `lan.switch.ports[3]{id,state,link_mode,blocked,flickering}` |
| `lan/stats` | `async_get_lan_stats` | diag | **200** | Non | `lan.stats{rx,tx,port[4]{index,rx{bandwidth,bytes,packets},tx{…}}}` |
| `alerts` | `async_get_the_list_of_user_alerts` | — | **200** | Non | `alerts.list[]` |
| `parentalcontrol` | `async_get_parental_control_service_state` | coord → switch Parental control | **401** | Oui | Non vérifiable |
| `parentalcontrol` (PUT), `parentalcontrol/hosts` (PUT) | `async_set_*` | switchs | non sondé (écriture) | — | — |
| `remote/proxywol` | `async_get_wakeonlan_configuration` | — | **401** | Oui | — |
| `services` | `async_get_bbox_services` | diag | **200** | Non | `services{firewall,dyndns,dhcp,dhcp6,nat,gamermode,upnp.igd,remote{proxywol,admin},parentalcontrol,wifischeduler,voipscheduler,notification,hotspot,usb{samba,printer,dlna}}` |
| `notification` | `async_get_events_notification_service` | — | **401** | Oui | — |
| `speedtest/info` | `speedtest.async_get_speedtest_infos` | coord → Speedtest download | **401** | Oui | Non vérifiable. L'endpoint **existe** (401 et non 404), donc `_speedtest_supported` restera vrai. |
| `voip/voicemail` | `voip.async_get_voip_voicemail` | diag | **404** | — | Absent sur ce firmware |
| `voip/callforward` | `async_get_voip_callforward` | — | **404** | — | Absent |
| `voip/calllog/{id}` (DELETE) | `async_del_voip_calllog_by_id` | — | non sondé (écriture) | — | — |
| `cpl` | `wan.async_get_wan_cpl` | — | **200** | Non | `cpl{running,list[]{…,associateddevice[]{…,endstations[]}}}` |
| `wan/cable` | `async_get_wan_cable` | — | **404** | — | Absent (FTTH) |
| `wan/ftth/stats` | `async_get_wan_ftth` | diag | **200** | Non | `wan.ftth{mode,state}` |
| `wan/diags` | `async_get_wan_diags` | — | **200** | Non | `diags{dns[24],ping[24],http[24]}{min,max,average,success,error,tries,status,protocol}` |
| `wan/ip` | `async_get_wan_ip` | coord → IP Address, IPv6 Address | **200** | Non | ✔ `wan.ip.address`, `wan.ip.ip6address[0].ipaddress`. En plus : `internet.state`, `link{state,type}`, `ip{cgnatenable,maptenable,ip6prefix[],…}` |
| `wan/ip/stats` | `async_get_wan_ip_stats` | coord → 10 capteurs de débit | **200** | Non | ✔ `rx/tx{packets,bytes,packetserrors,packetsdiscards,occupation,bandwidth,maxBandwidth,contractualBandwidth}`. `bytes` et `packets` sont des **str**, les autres des int (le `float()` du code les accepte ✔). |
| `wan/xdsl`, `wan/xdsl/stats` | `async_get_wan_xdsl*` | — | **404** | — | Absents (FTTH) |
| `wireless` | `wifi.async_get_wireless` | coord → switchs Wi-Fi | **401** | Oui | Non vérifiable. Le code attend `wireless.radio.{24,5,guest}.enable`. |
| `wireless` (PUT), `wireless/{24,5,guestenable}` (PUT) | `async_set_wireless*`, `async_set_wps` | switchs | non sondé (écriture) | — | — |
| `wireless/24/stats` | `async_get_stats_24` | diag | **401** | Oui | — |
| `wireless/5/stats` | `async_get_stats_5` | diag | **401** | Oui | Pas d'équivalent 6 GHz dans bboxpy |
| `wireless/wps` | `async_get_wps` | coord → switch Wps | **200** | Non | ✔ `wps{state,enable,timeout}` |
| `wireless/wps` (POST/DELETE) | `async_on_wps` / `async_off_wps` | — | non sondé (écriture) | — | — |
| `wireless/repeater` | `async_get_repeater` | diag | **401** | Oui | — |
| `device/reboot` (POST) | `device.async_reboot` | button Restart | non sondé (écriture) | — | — |
| `device/factory` (POST) | `device.async_reset` | — (**réinitialisation usine** exposée par la lib) | non sondé | — | — |
| `device/optimization` (PUT), `device/display` (POST) | `async_optimization`, `async_display` | — | non sondé | — | — |
| `dhcp` | *(non référencé par bboxpy)* | — | **200** | Non | `dhcp{state,enable,minaddress,maxaddress,leasetime}` |
| `nat/rules` | *(non référencé)* | — | **200** | Non | `nat{enable,rules[]{id,enable,description,externalip,externalport,internalport,internalip,protocol}}` |
| `upnp/igd` | *(non référencé)* | — | **200** | Non | `upnp.igd{state,uuid,friendlyname,enable}` : désactivé ✔ |

**Charge par cycle** (60 s par défaut) : 11 GET (`device`, `device/mem`, `device/led`, `hosts`, `wan/ip/stats`, `parentalcontrol`, `wireless/wps`, `wireless`, `wan/ip`, `device/cpu`, `speedtest/info`), chacun avec le paramètre `btoken`, plus `device/token` quand le jeton expire.

**Constat transverse** : une large part des données utiles est **publique sur le LAN**. Sans aucun identifiant, on obtient l'état du lien, les IP, les débits, les compteurs, l'uptime, le firmware, la température, la mémoire, les ports Ethernet, l'état Wi-Fi global, l'état du Wi-Fi invité, la liste nom/IP des hôtes et l'état UPnP. Pourtant, `bboxpy` s'authentifie avant **chaque** requête, y compris pour ces endpoints publics : `async_request` appelle `async_get_token`, qui appelle `async_auth` puis `POST login`.

---

## 3. Ce qui casse ou risque de casser

### 3.1 Hôte IP vs `mabbox.bytel.fr` (🔴 risque majeur)
- Le firmware 25.5.76 redirige systématiquement l'API appelée par IP vers `mabbox.bytel.fr`.
- aiohttp (`allow_redirects=True` par défaut) suit le 302. Pour un **POST**, il le transforme en GET et **abandonne le corps**, si bien que le mot de passe n'est jamais transmis. La connexion par IP (README : « The Bbox can be configured with its IP address ») échouera très probablement.
- Les cookies posés par l'IP (`CookieJar(unsafe=True)`) ne couvrent pas le domaine de redirection. La conservation de `?btoken=` lors de la redirection n'est pas garantie.
- **Contournement immédiat** : configurer l'hôte `mabbox.bytel.fr` (valeur par défaut) avec TLS. **Condition** : le DNS utilisé par HA doit renvoyer un **enregistrement A** vers la box, car bboxpy force `family=AF_INET`. C'est le cas sur le poste de sondage, mais cela reste à vérifier côté HA (question ouverte Q3).

### 3.2 Authentification et cycle de session (🔴)
- `BboxRequests._authenticated` passe à `True` après le premier login et n'est **jamais** réinitialisé. À l'expiration de la session de la box, `device/token` renvoie 401 et l'erreur `AuthorizationError` est convertie en `UpdateFailed` par le coordinateur. L'intégration reste indisponible jusqu'à un rechargement manuel. Ni nouvelle connexion ni flux de ré-authentification ne sont déclenchés.
- `ConfigEntryAuthFailed` n'est levé que dans `_async_setup`, autour d'un constructeur qui ne fait aucun appel réseau : c'est du code mort.
- Une session aiohttp propre est créée sans jamais être fermée : rien n'appelle `async_close()` au déchargement, et le config flow en crée une à chaque essai. Comme chaque changement d'options recharge l'entrée, chaque rechargement laisse fuir une session (« Unclosed client session »).
- `TCPConnector(verify_ssl=…)` est un paramètre déprécié d'aiohttp (remplacé par `ssl=`). Il produit un avertissement aujourd'hui et cassera au retrait.
- Non testé ici : verrouillage de la box après plusieurs logins, durée de vie de la session. Ces points sont à mesurer en terrain.

### 3.3 Robustesse du coordinateur (🟠)
- Le fallback de `_call()` (`{}`) est illusoire : `check_list({})` lève `UpdateFailed` et `merge_objects({})` lève une `AssertionError`. Une seule erreur sur `led`, `parentalcontrol`, `wps`, `wireless` ou `hosts` rend **toutes** les entités indisponibles.
- Les entités par appareil (trackers, contrôle parental) ne sont créées qu'au démarrage. Un nouvel appareil n'apparaît qu'après rechargement.
- `BboxDeviceTracker.mac_address` / `ip_address` lèvent `KeyError` si l'appareil disparaît de `hosts` (`self._device = {}`).
- Si `device` ne contient pas `serialnumber` (cas observé **sans** auth), tous les `unique_id` deviennent `ABC12345-…`, ce qui provoque des collisions dès qu'il y a deux box. La présence du champ **avec** auth reste à confirmer.

### 3.4 Capteurs : exactitude (🟠)
- **Uptime** : `state_class=SensorDeviceClass.DURATION` mélange les énumérations. Il faut `device_class=DURATION` et pas de `state_class` (ou `TOTAL_INCREASING`).
- **Occupation de la bande passante** : le code recalcule `bandwidth*100/maxBandwidth` au lieu d'utiliser le champ `occupation` fourni par la box. Sur la 5696b, `maxBandwidth` est plafonné à 1 Gbit/s alors que `contractualBandwidth` est supérieur (offre > 1 Gbit/s), et les deux méthodes donnent des valeurs d'un ordre de grandeur différent. L'unité de `occupation` (‰ ou Mbit/s ?) est à clarifier.
- `POWER_FACTOR` est employé pour des pourcentages (occupation, mémoire libre) : c'est un détournement de `device_class`.
- **Link status** lit `device.status`, l'état de la box, et non l'état du lien WAN. Le firmware expose `wan.link.state` (`Up`), `wan.internet.state` (int) et `wan.ftth.state`, plus pertinents.
- **Speedtest download** : l'endpoint existe (401), mais son schéma n'a pas été vérifié.

### 3.5 Spécificités 5696b / Wi-Fi 7 (🟠)
- **Bandes** : bboxpy ne gère que `24`, `5` et `guest`. Pas de `wireless/6/stats`, pas d'identifiant de bande 6 GHz. Le résumé public expose `guest24enable`, `guest5enable`, `compatibility24enable` et `compatibility5enable`, avec un SSID « compatibility » en plus du SSID principal. L'architecture semble donc reposer sur un SSID MLO principal et un SSID de compatibilité pour les anciens clients. Le 6 GHz reste invisible sans authentification.
- **Hôtes** : un nouveau champ `wirelessByBand[]` apparaît (vide pour un client filaire / CPL), à côté de l'ancien `wireless.band`. L'intégration ne s'en sert pas : pas de casse, mais une donnée MLO perdue.
- **Ports Ethernet** : `device/led.ethernetPort` contient 5 entrées, `lan/ip.switch.ports` 3 et `lan/stats.port` 4. Le nombre réel de ports physiques du modèle est à confirmer avant de garder 5 capteurs.
- **Champs absents** (vue sans auth) : `device.serialnumber`, `device.temperature`, `device.hwRevision`.
- **404 sur ce modèle** : `voip/voicemail`, `voip/callforward`, `wan/cable`, `wan/xdsl`, `wan/xdsl/stats`.

### 3.6 Dépendance à UPnP
**Aucune.** Pas de découverte SSDP dans le manifest, aucun appel `upnp/*` dans bboxpy ni dans l'intégration. L'intégration n'a pas besoin d'UPnP et le lit même comme désactivé (`upnp.igd.enable = 0`). UPnP pourra rester désactivé.

### 3.7 Compatibilité Home Assistant 2026.11
- **Testé** : sous HA **2026.10.4**, 17 tests sur 17 passent (CI amont du 2026-11-16). Le job échoue sur la couverture (78,67 % pour un seuil `--cov-fail-under=85`), pas sur un test. HA 2026.11.1 **n'a pas été testé** (`uv.lock` pointe sur 2026.10.4 et aucun environnement local n'existe).
- **Marketplace** : la validation échoue sur la vérification des assets de marque (« The repository does not provide brand assets ») : il faut ajouter `custom_components/bbox/brand/icon.png`. `hacs.json` déclare toujours `"homeassistant": "0.110.0"`, alors que le code exige au minimum une version 2024.x (`ConfigEntry[...]` / `runtime_data`, `DataUpdateCoordinator._async_setup`, `_abort_if_unique_id_mismatch`, `async_update_reload_and_abort(data_updates=)`).
- **API à moderniser** (aucune cassure constatée sous 2026.10.4) :
  - `FlowResult` → `ConfigFlowResult` (`config_flow.py`, étapes `user` et `init`) ;
  - `AddEntitiesCallback` → `AddConfigEntryEntitiesCallback` ;
  - `DataUpdateCoordinator(...)` sans `config_entry=` explicite : il repose sur la variable de contexte, et HA recommande de passer l'entrée ;
  - `async_create_clientsession` n'est utilisé qu'en ré-authentification. Partout ailleurs, la lib crée sa propre `ClientSession`.
- **Bon point** : async de bout en bout, `runtime_data`, `OptionsFlow()` sans argument (style actuel), `async_forward_entry_setups`.
- **Identité** : `manifest.json` pointe vers `cyr-ius` (`codeowners`, `documentation`, `issue_tracker`). Le domaine `bbox` est partagé avec l'amont : les deux ne peuvent pas coexister dans la même instance HA.

---

## 4. Inventaire des entités (version lecture seule)

### 4.1 À SUPPRIMER (écrivent sur la box)

| Entité | Plateforme | Appel d'écriture |
|---|---|---|
| Parental control (global) | switch | `PUT parentalcontrol` |
| Parental control (par appareil, ×N) | switch | `PUT parentalcontrol/hosts` |
| Wps | switch | `PUT wireless?wps.enable=` |
| Wifi (all) | switch | `PUT wireless?radio.enable=` |
| Wifi 2.4Ghz | switch | `PUT wireless/24` |
| Wifi 5Ghz | switch | `PUT wireless/5` |
| Wifi Guest | switch | `PUT wireless/guestenable` |
| Restart | button | `POST device/reboot` |

**Pas de bouton « sonnerie »** dans la version 1.5.4 : il n'existe ni entité ni méthode bboxpy correspondante. Seul `summary.diags[].ring_test` est exposé en lecture. Il n'y a donc rien à retirer de ce côté.

Le retrait de la plateforme `switch` fait disparaître la plateforme entière. Il faudra nettoyer les entités orphelines du registre lors de la migration.

Au-delà des entités, `bboxpy` expose aussi `device/factory` (réinitialisation usine), `device/optimization`, `device/display`, `wireless/wps` en POST/DELETE et `voip/calllog` en DELETE. Ce sont des arguments pour un client **sans aucune méthode d'écriture** (§5).

### 4.2 À GARDER

| Entité | Source | Remarque |
|---|---|---|
| System Temperature | `device/cpu` (m°C) | ✔ public |
| Downloaded / Uploaded | `wan/ip/stats` | ✔ public |
| Download / Upload speed | `wan/ip/stats` | ✔ public |
| Download / Upload error, discard packet | `wan/ip/stats` | ✔ public. Sans unité ni `state_class` ; à désactiver par défaut ? |
| Download / Upload bandwidth occupation | `wan/ip/stats` | À corriger (§3.4) |
| IP Address / IPv6 Address | `wan/ip` | ✔ public |
| Boot counter | `device` | ✔ public |
| Uptime | `device` | Corriger `device_class`. Mieux encore : un horodatage de démarrage. |
| Memory free | `device/mem` | ✔ public |
| Ethernet port 1-5 | `device/led` | Nombre de ports à confirmer |
| Link status | `device` | Remplacer la source par `wan.link.state` / `internet.state` |
| Refresh (bouton) | local | Aucune écriture sur la box |
| Device trackers | `hosts` | **Exige une authentification** (décision Q1/Q2) |
| Speedtest download | `speedtest/info` | **Exige une authentification**. Désactivé par défaut. |

### 4.3 À AJOUTER (lecture seule, données publiques sauf mention)

| Proposition | Source | Type |
|---|---|---|
| Wi-Fi activé (global) | `summary.wireless.radio` / `status` | binary_sensor |
| Wi-Fi invité activé (global, 2,4, 5) | `summary.wireless.guest*enable` | binary_sensor |
| SSID de compatibilité activé | `summary.wireless.compatibility*enable` | binary_sensor |
| WPS activé | `wireless/wps.enable` | binary_sensor (remplace le switch) |
| UPnP IGD activé | `upnp/igd.enable` ou `services.upnp.igd.enable` | binary_sensor (sentinelle : doit rester off) |
| Lien WAN / Internet / FTTH | `wan/ip.link.state`, `internet.state`, `wan/ftth/stats.state` | binary_sensor |
| IPv6 opérationnel | `wan/ip.ip.ip6state` | binary_sensor |
| Type de lien | `wan/ip.link.type` | sensor (diagnostic) |
| Débit contractuel descendant / montant | `wan/ip/stats.*.contractualBandwidth` | sensor |
| Version du firmware | `device.main.version` | sensor diagnostic (déjà `sw_version`) |
| Nombre d'appareils connus | `len(summary.hosts)` | sensor. Inactifs inclus ? À valider. |
| Nombre d'alertes | `summary.alerts.count` | sensor |
| Latence ping / DNS / HTTP | `wan/diags` (dernier point) | sensor |
| Trafic LAN rx/tx | `lan/stats` | sensor |
| État Wi-Fi par bande, 6 GHz, MLO | `wireless`, `wireless/*/stats` | **Exige une authentification** : schéma à relever |

---

## 5. Recommandation bboxpy

| Option | Pour | Contre |
|---|---|---|
| **Figer 1.4.1** (état actuel) | Zéro effort | Garde les défauts (§3.1 à 3.3), pas de mode sans mot de passe, pas de 6 GHz, embarque des méthodes d'écriture dont une réinitialisation usine |
| **Maintenir le fork bboxpy** | Correctifs propres, réutilisable | Publication PyPI sous un autre nom, double dépôt, double CI et releases synchronisées pour un seul mainteneur. `manifest.requirements` doit pointer vers PyPI (les URL git sont fragiles dans HA). |
| **Vendoriser bboxpy tel quel** | Plus de dépendance externe | bboxpy est **GPL-3.0-or-later** et hass-bbox2 est **MIT** : copier le code imposerait la GPL à l'intégration distribuée. On embarquerait aussi tout le code d'écriture. |
| **Client interne minimal, réécrit** (recommandé) | ~150 lignes MIT dans `custom_components/bbox/`, **GET uniquement**. Garantie lecture seule vérifiable par lecture du code. Mot de passe optionnel. Session HA. Reconnexion sur 401. Gestion de l'hôte canonique. Plus aucune dépendance. | Code à écrire et à tester (les fixtures existent). La liste d'endpoints est un fait d'API, pas du code à recopier. |

**Recommandation**
- **Court terme** : garder `bboxpy==1.4.1` figé, le temps de retirer les entités d'écriture (story S2), pour ne pas mélanger les changements.
- **Moyen terme** : remplacer bboxpy par un client interne en lecture seule (S4), puis retirer la dépendance du manifest.
- **Ne pas maintenir le fork `bboxpy`**. Il peut rester comme référence, mais rien n'y est poussé. Le cas échéant, le signaler en archive.

---

## 6. Prochaines étapes (stories courtes)

1. **S1, socle du fork** : `manifest.json` (`codeowners`, `documentation`, `issue_tracker` → fork, version `1.6.0-dev`), `hacs.json` (version HA minimale réaliste), `brand/icon.png`, CI du fork au vert (tests + validate). Ajuster le seuil de couverture ou compléter les tests, puis épingler HA 2026.11.x dans `uv.lock`.
2. **S2, retrait des écritures** : supprimer `switch.py`, le bouton Restart et les traductions associées. Garder Refresh. Nettoyer les entités orphelines. Tests mis à jour.
3. **S3, corrections capteurs** : `device_class` de l'Uptime, occupation (utiliser `occupation` ou `contractualBandwidth`, après clarification), `device_class` des pourcentages, source du « Link status ». Tolérance par endpoint dans le coordinateur : une erreur ne masque plus que les entités concernées.
4. **S4, client interne GET-only** : session HA, hôte canonique (`mabbox.bytel.fr`, pas de POST redirigé), mot de passe **optionnel**, reconnexion sur 401 → `ConfigEntryAuthFailed`, fermeture de session, `ssl=` à la place de `verify_ssl`. Fixtures 5696b anonymisées à partir des captures.
5. **S5, mode sans mot de passe** : config flow sans champ obligatoire, `unique_id` dérivé d'un identifiant public (MAC LAN de la box, cf. `lan/ip.mac`) et migration des `unique_id` existants si une instance est déjà installée.
6. **S6, nouveaux capteurs publics** (§4.3).
7. **S7 (optionnelle, selon Q1)** : relevé authentifié, fait **par Alex**, via le téléchargement des diagnostics HA (données expurgées par `TO_REDACT`), pour les schémas `hosts`, `wireless` (6 GHz / MLO), `speedtest/info` et `device` authentifié.
8. **S8, distribution** : release taguée sur le fork, ajout en dépôt personnalisé dans la Marketplace, test d'installation sur HA 2026.11.1.

---

## 7. Questions ouvertes pour Alex

1. **Mot de passe** : accepte-t-on que l'intégration s'authentifie (login + jeton) pour obtenir les appareils connectés, l'état Wi-Fi détaillé et le speedtest ? Ou vise-t-on un mode **strictement sans mot de passe** (données publiques uniquement, §4.3) ?
2. **Device trackers** : utiles ? Ils exigent l'authentification. Sans elle, seul le nombre d'hôtes et leurs noms/IP sont disponibles (`summary.hosts`), sans état actif ni MAC.
3. **DNS côté HA** : sur l'hôte HA, `mabbox.bytel.fr` résout-il en IPv4 vers la box ? Le DNS de HA OS pointe-t-il sur la box ou sur un autre résolveur (AdGuard, Pi-hole…) ?
4. **TLS** : peut-on vérifier, depuis HA, que le certificat présenté pour `mabbox.bytel.fr` est valide (`verify_ssl` par défaut) ?
5. **Instance existante** : l'intégration amont (domaine `bbox`) est-elle déjà installée dans HA ? Faut-il prévoir une migration des `entity_id` / `unique_id`, ou partir d'une installation propre ?
6. **Licence** : d'accord pour rester en MIT et écrire un client interne, plutôt que d'embarquer du code GPL ?
7. **Ports Ethernet** : combien de ports physiques sur la 5696b (l'API annonce 5, 4 ou 3 selon l'endpoint) ?
8. **Endpoints Wi-Fi 7** : autorises-tu, à une étape ultérieure, un GET unique sur des endpoints non référencés par bboxpy (par ex. `wireless/6/stats`) pour cartographier le 6 GHz ? Ils répondront probablement 401 sans authentification.
9. **Champ `occupation`** : l'unité exposée par la box (‰ du maximum ou Mbit/s) peut-elle être recoupée avec l'interface web de la box ?
