# Dirk-Jan's HA add-ons

Home Assistant add-on repository.

## Add-ons

### [HA Config Apply](./config_apply)

Past je GitHub-gehoste Home Assistant-config toe op een knopdruk. Haalt de
nieuwste `desired/` uit de config-repo, past de gewijzigde dashboards/automations
toe via het repo-eigen `apply_ha.py`, en verifieert het resultaat. Praat met HA
via de Supervisor-proxy: geen los HA-token, Protection mode kan aan blijven.

## Installeren

Instellingen → Add-ons → Add-on Store → ⋮ → Repositories → voeg toe:

```
https://github.com/dirkjanv_microsoft/ha-config-apply-addon
```

Zie [config_apply/DOCS.md](./config_apply/DOCS.md) voor de volledige uitleg.
