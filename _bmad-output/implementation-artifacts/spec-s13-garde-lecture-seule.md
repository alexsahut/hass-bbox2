---
title: 'S13 — Garde de lecture seule : aucune plateforme ni entité qui écrit vers la box'
type: 'chore'
created: '2026-11-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'a7026696b4a3a19d75f85e759519530af0f73828'
context: ['{project-root}/AGENTS.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La lecture seule de l'intégration n'est garantie que par le client (`BboxClient._request`) et par la fixture `read_only_guard`, qui ne contrôle que les requêtes émises pendant les tests. Rien n'empêche qu'on ajoute un jour une plateforme ou une entité d'action (interrupteur, nombre, sélecteur…) que les tests n'exercent pas.

**Approach:** Ajouter un test qui charge l'intégration et échoue si elle déclare une plateforme d'écriture (`switch`, `button`, `number`, `select`, `text`, `light`…) ou crée une entité dont la classe expose une action, sans modifier le code de l'intégration.

## Boundaries & Constraints

**Always:** le test porte sur ce que l'intégration déclare et crée réellement (constante `PLATFORMS`, entités enregistrées) ; son message d'échec nomme la plateforme ou l'entité fautive.

**Never:** aucune modification de `custom_components/bbox/` ; aucune requête vers une vraie box ; pas de liste de plateformes autorisées implicite (tout ajout doit faire échouer le test tant qu'il n'est pas explicitement admis).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| État actuel | `PLATFORMS` = sensor, binary_sensor, device_tracker, button (Refresh seul) | Test vert | N/A |
| Plateforme ajoutée | `Platform.SWITCH` (ou number, select, text, light…) dans `PLATFORMS` | Test rouge, plateforme nommée | Message d'assertion |
| Entité d'action ajoutée | Nouvelle classe d'entité héritant d'une entité d'action de HA | Test rouge, entité nommée | Message d'assertion |
| Autre bouton | Bouton de clé autre que `refresh` (ex. redémarrage) | Test rouge, entité nommée | Message d'assertion |
| Service ajouté | Service enregistré dans le domaine `bbox` | Test rouge, service nommé | Message d'assertion |

## Decisions

- **Bouton Refresh (Q1 = A, ClaudeBox, 2026-11-23) :** seul le bouton de clé `refresh` (classe `RefreshButton`) est admis dans la plateforme `button` ; tout autre bouton fait échouer le test. Aucun changement de code.
- **Services (Q2 = A, ClaudeBox, 2026-11-23) :** le test vérifie aussi qu'aucun service du domaine `bbox` n'est enregistré après le chargement.

</frozen-after-approval>

## Code Map

- `custom_components/bbox/__init__.py:27` -- `PLATFORMS` (sensor, binary_sensor, device_tracker, button) : source de vérité des plateformes ; à lire, pas à modifier.
- `custom_components/bbox/button.py` -- `RefreshButton(BboxEntity, ButtonEntity)`, clé `refresh`, `async_press` → `coordinator.async_request_refresh()`.
- `custom_components/bbox/sensor.py`, `binary_sensor.py`, `device_tracker.py` -- classes `BboxSensor`, `BboxBootTimeSensor`, `BboxBinarySensor`, `BboxDeviceTracker` (`ScannerEntity`) : aucune action.
- `tests/conftest.py` -- fixtures `box_factory` / box authentifiée et `read_only_guard` (à réutiliser, ne pas modifier).
- `tests/test_setup.py:16` -- `test_setup_entry` : modèle de chargement complet avec mot de passe (toutes les plateformes créées).

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_read_only.py` -- créer le test : (1) `PLATFORMS` ⊆ plateformes en lecture {sensor, binary_sensor, device_tracker} plus `button` ; (2) après chargement avec mot de passe, chaque entité de l'entrée appartient à un domaine admis et, pour `button`, seulement la clé `refresh` ; (3) aucun service du domaine `bbox` -- verrouille l'intention sans toucher au code.
- [x] `docs/maintenance/historique.md` -- ajouter la ligne S13 au tableau des stories -- traçabilité du fork.

**Acceptance Criteria:**
- Given le code actuel, when `uv run pytest tests/test_read_only.py` s'exécute, then le test passe.
- Given `Platform.SWITCH` ajouté localement à `PLATFORMS` (essai non commité), when le test s'exécute, then il échoue en nommant `switch`.
- Given la suite complète, when `uv run pytest` s'exécute, then elle passe avec une couverture ≥ 85 %.

## Implementation Notes

- 2026-11-23, étape 3 (sous-agent d'implémentation, sans contexte préalable) : `tests/test_read_only.py` créé (4 tests : plateformes déclarées, entités créées avec mot de passe et tous les hôtes suivis, registre, services du domaine `bbox`) ; ligne S13 ajoutée à `docs/maintenance/historique.md` avec le n° de PR #16 présumé (à vérifier à l'ouverture de la PR). Aucun fichier de `custom_components/` modifié.
- Vérifications rapportées par le sous-agent : `tests/test_read_only.py` 4 passés ; suite complète 237 passés, couverture 99,46 % ; ruff 0.17.5 sans écart ; essais temporaires annulés (plateforme `switch`, bouton `restart`, classe bouton + interrupteur, capteur + interrupteur, service `bbox.reboot`) : tous en échec avec un message nommant l'élément fautif.
- Essai négatif refait par l'orchestrateur : `Platform.SWITCH` ajouté localement à `PLATFORMS` → `test_platforms_are_read_only` échoue (`Platform(s) not admitted (write to the box?): ['switch']`) ; fichier restauré, `custom_components/` propre, rien de commité.
- Audit de la matrice (étape 3) NON SOLDÉ : la ligne « État actuel » est couverte par des tests qui tournent ; les lignes « Plateforme ajoutée », « Entité d'action ajoutée », « Autre bouton » et « Service ajouté » ne sont vérifiées que par des essais manuels annulés, pas par un test commité qui tourne. À faire avant l'étape 4 : tests unitaires des fonctions de refus (plateforme hors liste, bouton de clé autre que `refresh`, entité héritant d'une entité d'action, service `bbox` enregistré), ce qui demande d'extraire la vérification des plateformes et des services en fonctions testables dans le test.
- Arrêt volontaire (budget de temps du tour) : statut laissé `in-progress`, étapes 4 et 5 non commencées, rien de commité ni poussé.
- 2026-11-23, reprise de l'étape 3 (`bmad-build` relancé, implémentation directe par l'orchestrateur) : vérification des plateformes et des services extraite en fonctions (`_refused_platforms`, `_services`) ; ajout des tests de la matrice : plateforme ajoutée (`switch`, `number`, `select`, `text`, `light`), entité d'action (`SwitchEntity`, capteur héritant de `SwitchEntity`, `NumberEntity`), autre bouton (classe autre que `RefreshButton`, `RefreshButton` de clé `restart`), service `bbox.reboot` enregistré ; plus un contrôle positif (capteur, bouton `refresh`). `tests/test_read_only.py` : 16 passés ; suite complète : 249 passés, couverture 99,46 % ; ruff 0.17.5 sans écart.
- Audit de la matrice SOLDÉ : chaque ligne est couverte par un test commité qui tourne et passe.
- Essai négatif refait : `Platform.SWITCH` ajouté localement à `PLATFORMS` → `test_platforms_are_read_only` échoue (`Platform(s) not admitted (write to the box?): ['switch']`), comme les tests d'entités ; fichier restauré, `git diff` vide sur `custom_components/`.
- Arrêt volontaire avant l'étape 4 (revue interne au tour suivant) : statut laissé `in-progress`.

## Spec Change Log

## Review Triage Log

Revue du 2026-11-23, diff `a702669..73a3313` (19 kB), couches lancées : blind-hunter, edge-case-hunter, verification-gap (aucune sautée). Boucle 0, aucun intent_gap ni bad_spec.

| # | Source | Constat | Verdict | Route |
|---|--------|---------|---------|-------|
| R1 | verification-gap (gap), edge-case 1/2/7 | Les entités désactivées par défaut (`entity_registry_enabled_default=False`, 16 descriptions) n'atteignent jamais `platform.entities` (HA interrompt l'ajout), donc `_refusal` ne contrôle pas leur classe ; le registre ne contrôle que le domaine. Un capteur + `SwitchEntity` désactivé par défaut passerait. | medium | patch : activer toutes les entrées du registre de l'entrée, recharger, puis contrôler les entités |
| R2 | blind-hunter, edge-case 3 | `ACTION_ENTITIES` omet des classes qui agissent sans être des `ToggleEntity` (`Camera`, `CalendarEntity`, `AssistSatelliteEntity`, `TTSEntity`, `ConversationEntity`, `AITaskEntity`) : un hybride capteur + `Camera` passerait. | medium | patch : compléter le tuple |
| R3 | blind-hunter, edge-case 4 | `_refusal` lit `entity.entity_description.key` sans garde : un bouton sans description lève `AttributeError` au lieu de nommer l'entité. | low | patch : `getattr`, repli sur le nom de classe |
| R4 | blind-hunter | L'assertion « chaque plateforme a créé des entités » n'a pas de message nommant les plateformes vides. | low | patch : message |
| R5 | edge-case 5, blind-hunter | `test_no_service` et `test_registry_is_read_only` ne vérifient ni `LOADED` ni la présence du bouton `refresh` : passeraient à vide sur un chargement raté. | low | patch : assertions |
| R6 | blind-hunter | Ligne S13 de `historique.md` sans mention « sans release » ; le paragraphe Releases cite encore 233 tests. | low | patch : préciser « sans release » |
| R7 | blind-hunter, edge-case 6 | Un service enregistré hors du domaine `bbox` (ex. `notify.*`) ne serait pas détecté. | low | rejeté : l'intégration n'enregistre rien hors plateformes ; peu probable, et le correctif (instantané du registre de services avant/après, à filtrer des services des composants HA chargés) ajoute de la complexité |
| R8 | blind-hunter | Le mode sans mot de passe (`public_config_entry`) n'est pas chargé par le garde. | low | rejeté : entité d'action propre au mode public peu probable ; le correctif demande un second scénario d'assertions (pas de traceurs) |
| R9 | blind-hunter | Les tests de la matrice vérifient les fonctions (`_refused_platforms`, `_services`), pas les messages des tests de garde. | low | rejeté : les gardes appellent ces mêmes fonctions et leur message est prouvé par l'essai négatif ; le correctif (`pytest.raises` autour des gardes) ajoute de la complexité |
| R10 | blind-hunter, verification-gap (autre) | Spec : statut/notes obsolètes (« PR #16 présumé », « NON SOLDÉ »). | low | rejeté : correctif = édition de la spec. Fait : PR #16 confirmée ouverte sur `alexsahut/hass-bbox2` |
| R11 | blind-hunter | L'Approach gelée cite `button` parmi les plateformes à refuser, la décision Q1 l'admet pour Refresh. | false | rejeté : Q1 (ClaudeBox) tranche explicitement, pas de contradiction résiduelle ; correctif = édition de la spec |
| R12 | blind-hunter | `uv run pytest tests/test_read_only.py` sort en code 1 (seuil de couverture 85 % global sur un seul fichier), alors que l'AC dit « passe ». | low | rejeté : correctif = édition de la spec (`--no-cov`) ; les 16 tests passent et la suite complète satisfait le seuil |

Correctifs appliqués le 2026-11-23 (triage validé par ClaudeBox) :
- R1 : `test_entities_are_read_only` active toutes les entrées du registre de l'entrée, recharge l'entrée, et vérifie que chaque entrée du registre est une entité contrôlée (`Entity(ies) not checked`).
- R2 : `CalendarEntity` ajouté à `ACTION_ENTITIES` ; `camera`, `assist_satellite`, `tts`, `conversation`, `ai_task` refusés par le module d'une classe parente (`ACTION_COMPONENTS`), car leurs modules demandent des dépendances absentes des tests (`turbojpeg`, `hassil`, `mutagen`) ; aucune dépendance ajoutée. Tests : capteur + caméra (substitut de module `camera`), capteur + `CalendarEntity`.
- R3 : `_refusal` lit la clé par `getattr` et nomme la classe ; test d'un bouton sans description.
- R4 : message `Platform(s) without entity`.
- R5 : `LOADED` vérifié dans `test_registry_is_read_only` et `test_no_service` ; présence du seul bouton `refresh` dans le registre.
- R6 : ligne S13 de `historique.md` marquée « Sans release ».
Vérification : `tests/test_read_only.py` 19 passés ; suite complète 252 passés, couverture 99,46 % ; ruff 0.17.5 sans écart. Rien de différé.

## Verification

**Commands:**
- `uv run pytest tests/test_read_only.py` -- expected: vert
- `uv run pytest` -- expected: suite verte, couverture ≥ 85 %
- `uvx ruff@0.17.5 check . && uvx ruff@0.17.5 format --check .` -- expected: aucun écart

**Manual checks (if no CLI):**
- Essai local non commité : ajouter `Platform.SWITCH` à `PLATFORMS`, constater l'échec, annuler.

## Code Review (bmad-code-review, 2026-11-23)

Diff `a702669...c751ab1` (3 fichiers, +424), mode `full`. Couches : blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor (aucune en échec). Étapes 1–3 faites ; correctifs NON appliqués (arrêt au budget de temps du tour) ; #16 non fusionnée.

| # | Source | Constat | Verdict | Route |
|---|--------|---------|---------|-------|
| CR1 | blind-hunter, edge-case | `_refusal` repose sur une liste de classes interdites : une entité d'action absente de la liste passe (ex. `InfraredEmitterEntity`, `RadioFrequencyTransmitterEntity` de HA 2026.10), contraire au « tout ajout doit faire échouer » de la spec. | medium | patch : liste blanche par module — refuser toute classe parente de `homeassistant.components.<x>` hors `sensor`, `binary_sensor`, `device_tracker`, `button` (remplace `ACTION_ENTITIES`/`ACTION_COMPONENTS`) |
| CR2 | blind-hunter, verification-gap | Le cas `NumberEntity()` est refusé par le contrôle de classe, pas par la liste d'action ; seuls `ToggleEntity`, `CalendarEntity` et le substitut caméra atteignent les branches d'action. | low | patch : hybrides `SensorEntity` + classe d'action (`_SettingSensor` avec `NumberEntity`, etc.) |
| CR3 | verification-gap, acceptance-auditor | Le test R3 (`_NamedButton`) s'arrête au contrôle de classe et n'exerce pas le `getattr`. | low | patch : cas `RefreshButton` sans description, ou hybride capteur + bouton sans description |
| CR4 | verification-gap | Aucune sous-classe de `RefreshButton` de clé `refresh` n'est testée : retirer `type(entity) is not RefreshButton` ne ferait échouer aucun test. | low | patch : cas paramétré |
| CR5 | edge-case | `entries` lu avant le rechargement : une entrée créée au rechargement échapperait au contrôle « not checked ». | low | patch : relire les entrées après `async_reload` |
| CR6 | blind-hunter, edge-case | Entités ajoutées plus tard par un écouteur du coordinateur (motif `_add_ports`) non contrôlées. | low | patch : rafraîchir le coordinateur avant `_entities` |
| CR7 | blind-hunter, edge-case, acceptance-auditor | AC1 et Vérification : `uv run pytest tests/test_read_only.py` sort en code 1 (seuil de couverture global). | low | patch : `--no-cov` dans l'AC et la Vérification (hors bloc gelé) |
| CR8 | blind-hunter, acceptance-auditor | Notes d'implémentation contradictoires avec `status: done`. | low | patch : note de clôture |
| CR9 | blind-hunter | Test du registre redondant et lié au format du `unique_id`. | low | rejeté : le `unique_id` est l'identité du bouton ; doublon sans défaut |
| CR10 | blind-hunter | Nettoyage S2 des entités d'écriture absent de la Code Map. | low | rejeté : antérieur à S13, sans défaut |
| CR11 | blind-hunter | Mode sans mot de passe hors garde. | low | rejeté (R8, validé par ClaudeBox) |
| CR12 | blind-hunter, acceptance-auditor | `historique.md` : « 233 tests ». | false | rejeté : le chiffre décrit l'état à la release 2.0.3 |
| CR13 | acceptance-auditor | Tests de la matrice sur les fonctions, pas les messages des gardes. | low | rejeté (R9) |
| CR14 | acceptance-auditor | Reconnaissance par module testée seulement avec un substitut. | low | rejeté : absorbé par CR1 |
| CR15 | acceptance-auditor | Approach gelée : `button` parmi les plateformes d'écriture. | false | rejeté (R11) |

Reste ouvert : CR1 (medium) et CR2–CR8 (patch, low). Reprise : appliquer CR1–CR8, rejouer la Vérification, puis fusion si CI verte.
