# HA Config Apply — add-on

Past je GitHub-gehoste Home Assistant-config toe wanneer je op een knop drukt.

## Wat het doet

Wanneer je in HA op een knop drukt (`input_button.config_toepassen`), haalt de
add-on de nieuwste `desired/` uit je config-repo en past die toe via het
`apply_ha.py`-script uit diezelfde repo. Daarna verifieert het dat de live staat
overeenkomt, en schrijft het een korte status terug naar een tekstveld.

Geen pollen: er gebeurt alleen iets als jij drukt (ook via de HA-app op je mobiel).

## Waarom dit veilig is

- Praat met Home Assistant via de **Supervisor-proxy**, dus **geen los HA-token**
  nodig en **Protection mode kan aan blijven** (geen root/Docker-socket).
- De enige secret is een **alleen-lezen GitHub-token** met toegang tot alleen deze
  ene privé-repo.
- Past alleen `desired/`-wijzigingen toe; maakt vooraf een snapshot (rollback).

## Configuratie

| Optie | Betekenis |
|-------|-----------|
| `github_repo` | `owner/repo`, bijv. `dirkjanv_microsoft/home-assistant-config` |
| `github_ref` | branch, meestal `main` |
| `github_token` | fine-grained PAT, **Contents: Read-only** op alleen deze repo |
| `button_entity` | de knop-helper, bijv. `input_button.config_toepassen` |
| `status_entity` | tekstveld voor de status, bijv. `input_text.config_apply_status` |
| `apply_scope` | `changed` (alleen nieuwe wijzigingen) of `all` |

## Benodigde helpers in HA

Maak deze twee helpers aan (Instellingen → Apparaten & Services → Helpers), of
laat ze via de config-repo aanmaken:

- **Knop** (`input_button`): naam "Config toepassen" → `input_button.config_toepassen`
- **Tekst** (`input_text`): naam "Config apply status" → `input_text.config_apply_status`

Zet daarna een knop-kaart en het statusveld op een dashboard. Voorbeeld:

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
   Repositories → `https://github.com/dirkjanv_microsoft/ha-config-apply-addon`.
2. Installeer **HA Config Apply**.
3. Vul bij Configuratie de opties in (vooral `github_token`).
4. Start de add-on.

## Een alleen-lezen GitHub-token maken

GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate:
- **Resource owner**: jouw account
- **Repository access**: Only select repositories → `home-assistant-config`
- **Permissions** → Repository permissions → **Contents: Read-only**

Plak het token in de add-on-optie `github_token`.
