# Brand assets

Pre-sized copies of `docs/assets/logo.png`, laid out to match the directory structure the [home-assistant/brands](https://github.com/home-assistant/brands) repository expects for a custom integration:

```
custom_integrations/hu_energy_tariff/
├── icon.png       (256x256)
├── icon@2x.png     (512x512)
├── logo.png       (256x256)
└── logo@2x.png     (512x512)
```

This is what makes the logo show up in Home Assistant's own UI (the integrations list, the "Add Integration" dialog, the device page) - Home Assistant does not read icons from a custom integration's own repository. It fetches them from `home-assistant/brands`, keyed by domain (`hu_energy_tariff`). Until these files are submitted there via a PR against that repo (not this one), HA will show a generic default icon.

Not yet submitted - these are prepared and ready to go.
