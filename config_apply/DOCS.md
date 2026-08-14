# HA Config Apply — add-on

Past je GitHub-gehoste Home Assistant-config toe wanneer je op een knop drukt.

## Wat het doet

De add-on luistert op knop-drukken in Home Assistant en voert dan één van deze
acties uit (er wordt niet gepolld):

- **Config toepassen** (`input_button.config_toepassen`): haalt de nieuwste
  `desired/` op en past de gewijzigde dashboards/automations toe via
  `apply_ha.py`, met verificatie achteraf.
- **Config exporteren naar main** (`input_button.config_exporteren_naar_main`):
  leest de live HA-staat via `export_ha.py` en commit + pusht die **rechtstreeks
  naar `main`**.
- **Config exporteren naar branch** (`input_button.config_exporteren_naar_branch`):
  idem, maar commit naar een nieuwe `drift/<datum-tijd>`-branch en **opent een
  Pull Request**, zodat je de drift eerst kunt reviewen.

De status van de laatste actie komt in een tekstveld.

## Waarom dit veilig is

- Praat met Home Assistant via de **Supervisor-proxy**, dus **geen los HA-token**
  nodig en **Protection mode kan aan blijven** (geen root/Docker-socket).
- Er komt geen schrijftoegang tot HA van buiten je netwerk bij; export **leest**
  HA en **schrijft** naar GitHub.
- Apply maakt vooraf een snapshot (rollback). Export-naar-branch is reviewbaar
  via een PR.

> **Let op — token-rechten:** alleen *apply* volstaat met een **alleen-lezen**
> GitHub-token. De **export**-knoppen hebben een **read-write** token nodig
> (Contents: Read and write, en Pull requests: Read and write voor de PR-variant),
> gescoped op alleen deze ene repo.

## Configuratie

| Optie | Betekenis |
|-------|-----------|
| `github_repo` | `owner/repo`, bijv. `dirkjanv-prive/home-assistant-config` |
| `github_ref` | branch, meestal `main` |
| `github_token` | fine-grained PAT; **read-only** volstaat voor apply, **read-write** (Contents + Pull requests) nodig voor export |
| `button_entity` | apply-knop, bijv. `input_button.config_toepassen` |
| `export_main_button` | export-naar-main knop (leeg = uit) |
| `export_branch_button` | export-naar-branch knop (leeg = uit) |
| `status_entity` | tekstveld voor de status |
| `apply_scope` | `changed` (alleen nieuwe wijzigingen) of `all` |
| `git_name` / `git_email` | commit-identiteit voor export |

## Benodigde helpers in HA

Maak deze helpers aan (Instellingen → Apparaten & Services → Helpers):

- **Knop** "Config toepassen" → `input_button.config_toepassen`
- **Knop** "Config exporteren naar main" → `input_button.config_exporteren_naar_main`
- **Knop** "Config exporteren naar branch" → `input_button.config_exporteren_naar_branch`
- **Tekst** "Config apply status" → `input_text.config_apply_status`

Zet daarna de knop-kaarten en het statusveld op een dashboard. Voorbeeld:

```yaml
type: vertical-stack
cards:
  - type: button
    name: Config toepassen
    icon: mdi:cloud-download
    tap_action:
      action: perform-action
      perform_action: input_button.press
      target:
        entity_id: input_button.config_toepassen
  - type: entity
    entity: input_text.config_apply_status
    name: Status
```

## Installatie

1. Voeg de repository toe in HA: Instellingen → Add-ons → Add-on Store → ⋮ →
   Repositories → `https://github.com/dirkjanv-prive/ha-config-apply-addon`.
2. Installeer **HA Config Apply**.
3. Vul bij Configuratie de opties in (vooral `github_token`).
4. Start de add-on.

## Een alleen-lezen GitHub-token maken

GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate:
- **Resource owner**: jouw account
- **Repository access**: Only select repositories → `home-assistant-config`
- **Permissions** → Repository permissions → **Contents: Read-only**

Plak het token in de add-on-optie `github_token`.
