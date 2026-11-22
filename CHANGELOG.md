# Changelog

Ce fork (`alexsahut/hass-bbox2`) part de la version amont **1.5.4** de
[cyr-ius/hass-bbox2](https://github.com/cyr-ius/hass-bbox2). Les versions suivent
`MAJOR.MINOR.PATCH` (politique : `docs/maintenance/maintenance.md`, section 3).

## 2.0.3

Décodage des textes de la box (S12). Aucun `unique_id` ne change.

- **Textes encodés deux fois** : la box renvoie certains textes des hôtes encodés
  deux fois en UTF-8 (fabricant « GÃ©nÃ©rique » au lieu de « Générique »). Tout
  texte d'hôte (noms, `informations`, libellés du choix des appareils) est réparé :
  si, encodé en latin-1, il se décode en UTF-8, c'est cette version qui est
  retenue ; sinon il est laissé tel quel. Un texte déjà correct n'est pas modifié.
- Tests ajoutés.

## 2.0.2

Suivi d'appareils utilisable (S11). Aucun `unique_id` ne change.

- **Option « Appareils à suivre » (`tracked_devices`)** : remplace le booléen
  `track_devices`. Menu déroulant à choix multiple des hôtes connus de la box
  (en ligne en premier ; état et lien — Wi-Fi + bande, Ethernet — dans le libellé,
  en français si HA est en français). **Aucun appareil par défaut** ; seuls les
  appareils choisis ont un device tracker (activé) et un appareil HA. Sans mot de
  passe ou entrée non chargée : seul le rafraîchissement est réglable.
- **Noms lisibles** : `userfriendlyname`, sinon `hostname`, sinon « fabricant
  modèle », sinon le type ; la MAC seulement en dernier recours. Doublons suffixés
  par les 4 derniers caractères hexadécimaux de la MAC (« Acme Phone X (A1B2) »).
  Un nom donné par l'utilisateur n'est jamais écrasé.
- **Nettoyage au chargement** : les trackers et appareils d'hôtes de l'entrée qui
  ne sont pas choisis sont supprimés du registre, dont les 93 de la 2.0.1. L'appareil
  Bbox et les autres entités ne sont pas touchés. Sans mot de passe, tous sont retirés.
- **Migration** (`MINOR_VERSION` 2, `VERSION` inchangée à 1) : `track_devices`, vrai
  ou faux, devient `tracked_devices: []`. **Les trackers de la 2.0.1 ne sont pas
  recréés** : après la mise à jour, choisir ses appareils dans *Configurer*. Un retour
  à la 2.0.1 reste possible (la version majeure ne change pas) mais sans suivi, l'option
  `track_devices` n'existant plus.
- Fixture synthétique `hosts_synthetic.json` (pas une capture) ; tests ajoutés.

## 2.0.1

Correctif d'affichage, sans changement d'entité ni d'identifiant.

- Précision d'affichage (`suggested_display_precision`, 1 décimale) sur les
  capteurs en % (**Mémoire libre**, **Occupation du débit**
  descendant / montant), les **latences** ping / DNS / HTTP et la
  **température**. « Mémoire libre » s'affichait non arrondie
  (ex. 51.2167817312799 %). La valeur de l'état n'est pas arrondie : seul son
  affichage l'est, et une précision choisie dans HA par l'utilisateur reste
  prioritaire.

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

### Noms des entités et appareils suivis

- Noms des entités traduits (`translation_key`) : en français pour une instance
  HA en français, en anglais sinon. Plus aucun nom en dur.
- Option **Suivre les appareils connectés** désactivée par défaut : elle crée un
  device tracker et un appareil HA par hôte connu de la box (≈ capteur
  « Appareils connus »). L'activer seulement pour la présence via la box ; la
  couper ensuite laisse ces appareils orphelins.

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
