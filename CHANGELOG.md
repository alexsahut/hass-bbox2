# Changelog

Ce fork (`alexsahut/hass-bbox2`) part de la version amont **1.5.4** de
[cyr-ius/hass-bbox2](https://github.com/cyr-ius/hass-bbox2). Les versions suivent
`MAJOR.MINOR.PATCH` (politique : `docs/maintenance/maintenance.md`, section 3).

## 2.0.0

Première version du fork. Version **majeure** : des entités sont supprimées et
l'identifiant de la box (donc les `unique_id`) change. Voir « Incompatibilités ».

### Lecture seule

- Suppression de toutes les écritures sur la box : plateforme `switch` (Wi-Fi,
  Wi-Fi 2,4/5 GHz, Wi-Fi invité, WPS, contrôle parental global et par appareil)
  et bouton **Restart**. Les entités orphelines sont retirées du registre au
  chargement.
- Seul le bouton **Refresh** subsiste : il ne fait qu'interroger la box.

### Client API interne

- `bboxpy` (GPL) n'est plus utilisé : client interne `api.py` (MIT), aucune
  dépendance Python (`requirements: []`).
- Requêtes `GET` uniquement ; seul `POST` : le login, quand un mot de passe est
  configuré. Tout autre appel est refusé par le client, et les tests le vérifient.
- Session aiohttp de Home Assistant, TLS vérifié par défaut, redirections non
  suivies, erreurs explicites dans le config flow (redirection quand on utilise
  l'adresse IP, DNS, authentification, box injoignable, réponse invalide).
- Hôte par défaut `mabbox.bytel.fr`.
- Tolérance par endpoint : un endpoint en erreur ne rend indisponibles que ses
  entités ; un `404` est définitif (fonction absente du modèle).
- Reconnexion automatique sur `401` (un login, une seule nouvelle tentative).

### Mot de passe optionnel et masqué

- Mot de passe **facultatif** à la configuration et à la ré-authentification.
  Sans mot de passe, seuls les endpoints publics sont lus : ni device trackers
  ni capteur Speedtest.
- Champ masqué (type mot de passe) ; diagnostics expurgés (SSID, jetons, noms,
  adresses IP/IPv6, préfixes, passerelles, DNS, UUID, n° de série…).

### Identifiant de la box = adresse MAC LAN

- L'identifiant de l'entrée, de l'appareil Bbox, des entités et des device
  trackers est l'**adresse MAC LAN** de la box (`lan/ip`, endpoint public,
  normalisée). Il est identique avec et sans mot de passe.
- Le numéro de série n'est plus qu'une information de l'appareil ; la valeur de
  repli `ABC12345` disparaît.
- Ré-authentification : l'identifiant ne change pas ; si la MAC lue n'est pas
  celle de l'entrée, la ré-authentification est refusée (`wrong_account`).

### Reconfiguration

- Étape **Reconfigurer** (`async_step_reconfigure`) : changer l'hôte, TLS et la
  vérification du certificat, ajouter, remplacer ou retirer le mot de passe,
  sans supprimer l'entrée.
- Le mot de passe actuel n'est jamais renvoyé au formulaire : champ vide = mot
  de passe conservé ; case « Retirer le mot de passe » = données publiques
  seulement.
- La box lue doit être celle de l'entrée (même adresse MAC LAN), sinon abandon
  (`wrong_account`) et entrée inchangée. Les `unique_id` et `entity_id` sont
  conservés ; ajouter le mot de passe fait apparaître les device trackers.

### Capteurs corrigés

- **System Temperature** : classe température, °C, `measurement`.
- **Downloaded / Uploaded** : `data_size` en kB, `total_increasing`.
- **Download / Upload speed** : `data_rate` en kb/s.
- **Download / Upload bandwidth occupation** : en % du débit contractuel (et non
  plus du débit maximal du port, plafonné à 1 Gb/s) ; valeur brute de la box
  exposée dans un capteur désactivé par défaut.
- **Last boot** (horodatage) remplace **Uptime** (`info.device.uptime`,
  supprimé, historique non migré).
- **Link status** : `ON` si le lien WAN est `Up` (`wan.link.state`).
- **Ports Ethernet** : un binary_sensor par port réel (« Ethernet port N »),
  désactivés par défaut.

### Nouveaux capteurs (publics, sans mot de passe)

- binary_sensor : Wi-Fi activé, Wi-Fi invité activé, Wi-Fi invité 2,4 / 5 GHz,
  SSID de compatibilité 2,4 / 5 GHz, WPS activé, UPnP IGD activé (sentinelle
  `problem`), Lien FTTH, IPv6 opérationnel.
- sensor : Type de lien, Débit contractuel descendant / montant, Alertes,
  Appareils connus, Latence ping / DNS / HTTP, Trafic LAN reçu / émis.

### Incompatibilités avec l'amont (1.5.4)

- **Pas de migration depuis l'intégration amont.** Les `unique_id` amont
  reposaient sur le numéro de série (ou `ABC12345`) ; ceux du fork reposent sur
  l'adresse MAC LAN. Une installation existante de l'amont n'est **pas**
  convertie : supprimer l'entrée amont puis configurer le fork (les entités sont
  recréées, sans reprise de l'historique). Aucune instance du fork n'était
  installée avant cette version, d'où l'absence de conversion.
- Entités supprimées : tous les `switch`, le bouton **Restart**, le capteur
  **Uptime**.
- Le domaine reste `bbox` : l'intégration personnalisée surcharge l'intégration
  native `bbox` de Home Assistant (avertissement attendu au démarrage).
- Sans mot de passe, les device trackers et le capteur Speedtest ne sont pas
  créés (et sont retirés s'ils existaient).
