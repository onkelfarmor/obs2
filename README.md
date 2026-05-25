# obs2 – Home Assistant Integrationer

Dette repository indeholder to Home Assistant custom integrations:

| Integration | Beskrivelse |
|-------------|-------------|
| **Navimow** | Segway Navimow plæneklipper — status, kontrol, batteri og GPS-stivisualisering |
| **MinForsyning** | KMD Easy Energy vandforbrug — sensorer til Energy Dashboard |

---

## Installation via HACS (anbefalet)

1. Åbn HACS i Home Assistant.
2. Klik på **⋮ → Brugerdefinerede repositories**.
3. Indsæt `https://github.com/onkelfarmor/obs2` og vælg kategori **Integration**.
4. Søg efter **Navimow** eller **MinForsyning** og installer.
5. Genstart Home Assistant.

---

# Navimow – Segway Navimow plæneklipper

Integrerer Segway Navimow plæneklippere med Home Assistant via Navimows cloud-API og MQTT.

## Konfiguration

1. Gå til **Indstillinger → Enheder og tjenester → Tilføj integration**.
2. Søg efter **Navimow** og klik på den.
3. Log ind med din Navimow-konto (åbner Navimows login-side).
4. Angiv GPS-koordinaterne for din dokke-station (bruges til at omregne klipperens relative position til rigtige kortkoordinater).

> Dokke-koordinaterne finder du i Google Maps ved at holde fingeren nede på dok-placeringen.

## Enheder

Integrationen opretter følgende per klipper:

| Entity | Beskrivelse |
|--------|-------------|
| `lawn_mower.<navn>` | Klipperens status + Start / Pause / Dok-knapper |
| `sensor.<navn>_batteri` | Batteriniveau i % |
| `sensor.<navn>_klippefremgang` | Klipningens fremgang i % |
| `device_tracker.<navn>_position` | Klipperens GPS-position på kortet |
| `image.<navn>_klippesti` | Realtids PNG-visualisering af klippestien (via MQTT) |

## Lovelace – Kort visning

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: lawn_mower.navimow_din_klipper
    features:
      - type: lawn-mower-commands
        commands:
          - start_mowing
          - pause
          - dock
  - type: picture-entity
    entity: image.navimow_din_klipper_klippesti
    show_state: false
    show_name: false
```

## Fejlsøgning

```yaml
logger:
  logs:
    custom_components.navimow: debug
```

---

# MinForsyning – Home Assistant Custom Integration

Henter dagligt vandforbrug fra **MinForsyning (KMD Easy Energy)** og eksponerer det som sensorer i Home Assistant – klar til Energy Dashboard og automatiseringer.

---

## Installation

### Manuel
1. Kopiér mappen `custom_components/minforsyning/` til din HA-konfigurationsmappe under `custom_components/`.
2. Genstart Home Assistant.

### HACS
Se installationsvejledningen øverst i dette dokument.

### Manuel
1. Kopiér mappen `custom_components/minforsyning/` til din HA-konfigurationsmappe under `custom_components/`.
2. Genstart Home Assistant.

---

## Konfiguration

1. Gå til **Indstillinger → Enheder og tjenester → Tilføj integration**.
2. Søg efter **MinForsyning**.
3. Udfyld:
   | Felt | Beskrivelse |
   |------|-------------|
   | E-mail | Din login-e-mail på MinForsyning |
   | Adgangskode | Din adgangskode |
   | Forsyningsnummer | Utility-nummeret fra URL'en (standard: `0654000`) |

Forsyningsnummeret finder du i login-URL'en som parametret `utility=XXXXXX`. Har du adgang via en anden forsyning, skal du ændre dette.

---

## Sensorer

Integrationen opretter fire sensorer pr. konto:

| Sensor | Beskrivelse | Enhed |
|--------|-------------|-------|
| `sensor.minforsyning_vandforbrug_i_gar` | Forbrug dagen før (mest pålidelig) | m³ |
| `sensor.minforsyning_vandforbrug_i_dag` | Forbrug i dag (kan være ufuldstændig) | m³ |
| `sensor.minforsyning_vandforbrug_denne_maned` | Akkumuleret forbrug denne måned | m³ |
| `sensor.minforsyning_vandforbrug_i_ar` | Akkumuleret forbrug i år | m³ |

Sensoren **i går** indeholder også attributten `last_7_days` med de seneste 7 dages daglige forbrug som dictionary.

### Energy Dashboard
Integrationen skriver automatisk historiske daglige værdier ind i Home Assistants **long-term statistics** under ID'et `minforsyning:water_consumption_daily`. Tilføj den som vandkilde i Energy Dashboard under:

**Indstillinger → Energi → Vandforbrug → Tilføj vandkilde**

---

## Fejlsøgning

Aktiver debug-logging i `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.minforsyning: debug
```

Debug-loggen viser hvilke API-endpoints der afprøves og de rå svar fra serveren. Dele dette med udvikleren gør det muligt at tilpasse endpoint-discovery.

### Kendte begrænsninger
- Kræver e-mail/adgangskode login (ikke MitID eller NemID).
- API-endpoints til forbrugsdata er reverse-engineered og kan ændre sig ved opdateringer af KMD-platformen.
- Dataopdatering sker én gang i timen.

---

## Teknisk detaljer

Login-flowet bruger **PKCE OAuth2** (Authorization Code Flow med S256 code challenge) mod KMD Easy Energy Identity Server. Tokens gemmes i HA's config entry og fornyes automatisk via refresh token.
