# Fixtures Bbox F@st 5696b (firmware 25.5.76)

Réponses réelles de l'API `https://mabbox.bytel.fr/api/v1/<endpoint>` capturées
le 2026-11-19 **sans authentification**, puis anonymisées avant ajout au dépôt :
adresses IPv4/IPv6, adresses MAC, noms d'hôtes, fabricants/modèles d'appareils,
domaines, UUID, règles NAT et dates de première utilisation remplacés par des
valeurs fictives (plages de documentation 203.0.113.0/24 et 2001:db8::/32,
MAC localement administrées 02:00:00:00:00:xx). La structure JSON est intacte.

- Les versions de firmware des CPL (`cpl.json`) ne sont pas anonymisées : elles
  contiennent des numéros de version en `a.b.c.d` qui ne sont pas des adresses IP.
- Fichier `<endpoint>.json` : `/` remplacé par `_` (ex. `wan_ip_stats.json` = `wan/ip/stats`).
- `_status.json` : code HTTP obtenu pour chaque endpoint. Les endpoints en 401
  (hosts, wireless, speedtest/info, device/summary, parentalcontrol…) n'ont que le
  corps d'erreur : aucune capture authentifiée n'existe. En 404 : endpoints absents
  sur cette box (xDSL, câble, VoIP).
- Accès par l'IP de la box (`https://192.168.1.1/api/v1/...`) : réponse
  `302 Found` avec `Location: https://mabbox.bytel.fr:443/api/v1/<endpoint>` et
  corps vide.
