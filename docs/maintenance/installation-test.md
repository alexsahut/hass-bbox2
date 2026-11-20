# Procédure de test d'installation (release 2.0.0)

Pour Alex et la session ClaudeBox « Entrée et garage ». Cible : Home Assistant 2026.11.x,
Bbox Sagemcom **F@st 5696b** (FTTH, firmware 25.5.76 au moment de l'analyse).

Cette procédure s'exécute **après** la publication de la release `2.0.0` (tag posé avec le go
d'Alex). Chaque étape a un résultat attendu : noter tout écart, avec une capture, avant de continuer.

## 0. Prérequis

- [ ] **Sauvegarde complète de HA** (Paramètres → Système → Sauvegardes), ou snapshot de la VM qui
      porte HA. Noter son nom et son heure : c'est le point de retour arrière (§9).
- [ ] La release `2.0.0` existe sur <https://github.com/alexsahut/hass-bbox2/releases>, avec
      l'archive `bbox.zip`.
- [ ] Depuis HA, `mabbox.bytel.fr` se résout vers la Bbox (sinon l'erreur « dns_error » sera
      affichée à la configuration).
- [ ] Le mot de passe de l'interface d'administration de la Bbox est disponible ; **Alex le saisit
      lui-même** au §5. Il n'apparaît dans aucune note, capture ni conversation.
- [ ] Aucune intégration `bbox` n'est déjà configurée en YAML (`bbox:` dans `configuration.yaml`).

## 1. Ajouter le dépôt

1. Marketplace (HACS) → menu ⋮ → **Dépôts personnalisés**.
2. Dépôt `https://github.com/alexsahut/hass-bbox2`, catégorie **Integration** → **Ajouter**.

Attendu : « Bouygues Bbox » apparaît dans la liste, avec le dépôt `alexsahut/hass-bbox2`.

## 2. Installer la release

1. Ouvrir **Bouygues Bbox** → **Télécharger**.
2. Choisir la version **2.0.0** (pas une branche).

Attendu : la Marketplace installe `bbox.zip` de la release dans `custom_components/bbox`, et
demande un redémarrage.

## 3. Redémarrer Home Assistant

Paramètres → Système → **Redémarrer**.

Attendu dans le journal (Paramètres → Système → Journaux, journal complet) :
- l'avertissement **« We found a custom integration bbox which has not been tested by Home
  Assistant »** et le signalement que l'intégration personnalisée **surcharge l'intégration
  native `bbox`** (« custom integration overrides core integration »). C'est **attendu** : ce n'est
  pas une erreur (voir `maintenance.md`, §4 et §8) ;
- aucune erreur d'import du module `custom_components.bbox`.

## 4. Configuration sans mot de passe

Paramètres → Appareils et services → **Ajouter une intégration** → **Bouygues Bbox**.

- Hôte : `mabbox.bytel.fr` (valeur par défaut), TLS coché, vérification du certificat cochée.
- Mot de passe : **vide**.

Attendu :
- l'entrée est créée, titre « Bouygues Bbox » ;
- un appareil **Bbox** : fabricant Bouygues, modèle `F@st5696b`, version du firmware ; **sans**
  numéro de série (il n'est pas lisible sans mot de passe) ;
- la page de l'intégration indique « Intégration personnalisée », version **2.0.0** ;
- **aucun** device tracker, **aucun** capteur « Speedtest download ».

Contrôle négatif (facultatif) : avec l'adresse IP de la box comme hôte, l'erreur « redirect »
demande d'utiliser `mabbox.bytel.fr`. Annuler ensuite.

## 5. Ajout du mot de passe (saisi par Alex)

La version 2.0.0 n'a pas d'étape « Reconfigurer » : le formulaire de ré-authentification n'apparaît
que si la box **refuse** un mot de passe. Une entrée créée sans mot de passe ne peut donc pas en
recevoir un depuis l'interface ; on la supprime puis on la recrée.

1. Noter la liste des `entity_id` de l'entrée (Paramètres → Entités, filtre « Bouygues Bbox »).
2. Appareils et services → Bouygues Bbox → ⋮ → **Supprimer** l'entrée.
3. **Ajouter une intégration** → Bouygues Bbox, même hôte, et **Alex** saisit le mot de passe dans le
   champ masqué.

Attendu :
- l'entrée est créée ;
- **les entités publiques retrouvent les mêmes `entity_id`** : leur `unique_id` repose sur
  l'adresse MAC LAN, identique avec ou sans mot de passe, et HA restaure l'`entity_id` d'une entité
  supprimée recréée avec le même `unique_id`. Aucun doublon d'appareil Bbox ni d'entité suffixée
  `_2` ;
- le numéro de série apparaît dans les informations de l'appareil Bbox ;
- les device trackers des appareils connectés apparaissent (option « Suivre les appareils
  connectés », active par défaut), rattachés à l'appareil Bbox ;
- le capteur « Speedtest download » existe, **désactivé** par défaut.

## 6. Vérifications capteur par capteur (F@st 5696b)

Valeurs observées lors de l'analyse du 2026-11-19 ; ordre de grandeur attendu, pas valeur exacte.
« Désactivé » : l'entité existe mais est désactivée par défaut ; l'activer pour la vérifier, puis
attendre un cycle (60 s).

| Entité | Attendu |
|---|---|
| Link status | `Connecté` (on) |
| Lien FTTH | `Connecté` (on) |
| Type de lien | `1000baseT-HD` (catégorie diagnostic) |
| IPv6 opérationnel | on si l'accès a une IPv6 (adresse `Preferred`) |
| IP Address / IPv6 Address | adresses publiques de l'accès (ne pas les recopier dans un rapport) |
| Débit contractuel descendant / montant | ≈ 8 000 000 / 1 000 000 kb/s (8 Gb/s / 1 Gb/s) |
| Download / Upload speed | kb/s, varie avec le trafic |
| Download / Upload bandwidth occupation | % faible (0–5 % au repos), borné 0–100 |
| Downloaded / Uploaded | kB, croissant |
| System Temperature | °C plausible (≈ 40–70), lue via le repli CPU |
| Memory free | % entre 0 et 100 |
| Boot counter | entier stable |
| Last boot | date du dernier redémarrage, stable d'un cycle à l'autre (pas de nouvel état chaque minute) |
| Wi-Fi activé | reflète l'état réel du Wi-Fi |
| Wi-Fi invité activé | reflète l'état réel (off si pas de Wi-Fi invité) |
| WPS activé | reflète l'état réel |
| UPnP IGD activé | **off** (UPnP désactivé sur la box) ; « on » s'afficherait comme un problème |
| Alertes | nombre entier (souvent 0) |
| Appareils connus | nombre d'hôtes connus de la box (pas seulement les actifs) |
| Latence ping | quelques ms (≈ 7 ms) ; jamais 0 ms (inconnu si pas de mesure) |
| Latence DNS / HTTP (désactivés) | ms (HTTP ≈ 23 ms) |
| Trafic LAN reçu / émis (désactivés) | Go, croissant |
| Ethernet port 1…5 (désactivés) | `Up` sur les ports câblés, `Down` sinon |
| Download / Upload occupation (raw), discard/error packet (désactivés) | entiers |
| Speedtest download (mot de passe, désactivé) | kb/s du dernier test de la box |
| Device trackers (mot de passe) | `home` pour les appareils connectés ; passage à `away` 1 à 2 min après une déconnexion |
| Bouton Refresh | l'appui relance une lecture ; **aucun effet sur la box** |

Vérifier aussi qu'aucune entité ne permet d'agir sur la box (pas de switch, pas de bouton Restart).

## 7. Diagnostics expurgés

Appareils et services → Bouygues Bbox → ⋮ → **Télécharger les diagnostics**.

Attendu : un fichier JSON avec `entry`, `data` et `raw`. Les champs sensibles valent
`**REDACTED**` : mot de passe, jetons, SSID, adresses MAC et IP, numéro de série, noms d'hôtes,
UUID. Le parcourir avant de le partager ; le joindre au rapport seulement si rien de sensible n'y
reste en clair (sinon signaler le champ en cause, sans sa valeur).

## 8. (Optionnel, décision d'Alex) Supprimer l'ancienne intégration UPnP « Bbox »

Étape **séparée**, à ne faire que sur décision explicite d'Alex : elle n'est pas nécessaire au test
du fork.

Contexte : une ancienne intégration **UPnP/IGD** nommée « Bbox » est configurée mais morte (UPnP
désactivé sur la box) et porte 17 entités indisponibles. Elle n'a aucun lien avec ce fork (domaine
`upnp`, pas `bbox`).

1. Paramètres → Appareils et services → intégration **UPnP/IGD** → entrée « Bbox ».
2. Vérifier qu'il s'agit bien de l'entrée UPnP (et pas de « Bouygues Bbox ») et noter le nombre
   d'entités (17 attendues).
3. Menu ⋮ → **Supprimer**.

Attendu : les 17 entités disparaissent ; l'entrée « Bouygues Bbox » et ses entités sont intactes.
La sauvegarde du §0 permet de revenir en arrière.

## 9. Retour arrière

Si le test échoue ou si Alex le décide :

1. Appareils et services → **Bouygues Bbox** → ⋮ → **Supprimer** l'entrée.
2. Marketplace → **Bouygues Bbox** → ⋮ → **Supprimer** (désinstaller), puis retirer le dépôt
   personnalisé si on ne le garde pas.
3. Redémarrer HA : l'intégration native `bbox` n'est plus surchargée.
4. Si l'état de HA doit revenir exactement à l'avant-test (historique, registre, intégration UPnP
   supprimée…) : **restaurer la sauvegarde** (ou le snapshot de la VM) du §0.

## Rapport

Pour chaque étape : OK / écart (avec capture). Ne jamais y recopier le mot de passe, les adresses
IP/MAC publiques ni le numéro de série.
