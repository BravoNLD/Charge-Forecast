\# 🔋 Charge Forecast - Optimale laadmomenten voor thuisaccu \& EV



\[!\[hacs\_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

\[!\[GitHub release](https://img.shields.io/github/release/BravoNLD/Charge-Forecast.svg)](https://github.com/BravoNLD/Charge-Forecast/releases)



Vindt automatisch het \*\*goedkoopste 3-uurs laadblok\*\* voor je thuisbatterij of elektrische auto, gebaseerd op EPEX dag-ahead prijsvoorspellingen.



---



\## 🎯 Wat doet deze integratie?



Deze integratie analyseert EPEX stroomprijs-forecasts en identificeert de optimale momenten om te laden. In plaats van een enkel uur te kiezen, zoekt het naar het goedkoopste \*\*aaneengesloten blok\*\* (standaard 3 uur) door middel van een \*\*rolling window\*\*:

Rolling window analyse (3-uurs blok in komende 24 uur):

00:00-03:00 → gemiddeld €12,50/kWh 01:00-04:00 → gemiddeld €11,80/kWh ← BESTE BLOK 02:00-05:00 → gemiddeld €12,10/kWh 03:00-06:00 → gemiddeld €13,20/kWh ...


Perfect voor:
- ⚡ Thuisbatterijen (3-6 uur laden)
- 🚗 Elektrische auto's (volledige laadsessies)
- 🔥 Boilers en warmtepompen
- 🏭 Andere grote verbruikers met flexibele planning

---

## 📦 Installatie

### Vereisten

1. **Home Assistant** 2024.1 of nieuwer
2. **NED Energy Forecast** integratie: [github.com/BravoNLD/NED-forecast](https://github.com/BravoNLD/NED-forecast)
   - Deze moet **eerst** geïnstalleerd en geconfigureerd zijn
   - De `sensor.forecast_epex_price` moet actief zijn

### Stap 1: Installeer via HACS (aanbevolen)

1. Open HACS → Integrations
2. Klik rechtsbovenin op **⋮** → **Custom repositories**
3. Voeg toe:
   - **Repository**: `https://github.com/BravoNLD/Charge-Forecast`
   - **Category**: Integration
4. Klik **Charge Forecast** → **Download**
5. Herstart Home Assistant

### Stap 2: Configuratie

1. Ga naar **Instellingen** → **Apparaten & Services**
2. Klik **Integratie toevoegen** en zoek naar **Charge Forecast**
3. Stel de **laadduur** in (standaard 3 uur):
   - Thuisbatterij: 3-6 uur
   - EV snelladen: 2-3 uur
   - EV langzaam laden: 6-8 uur
4. Klik **Indienen**

✅ De integratie maakt nu 5 sensoren aan!

---

## 📊 Sensoren

Na configuratie krijg je **5 sensoren** voor verschillende planningshorizonten:

| Entity ID | Horizon | Gebruik |
|-----------|---------|---------|
| `sensor.charge_forecast_best_block_24h` | 24 uur | Dagelijkse optimalisatie (direct laden vandaag/vannacht) |
| `sensor.charge_forecast_best_block_36h` | 36 uur | Planning t/m volgende dag ochtend |
| `sensor.charge_forecast_best_block_72h` | 3 dagen | Weekendplanning (bijv. vrijdagavond voor zondagochtend) |
| `sensor.charge_forecast_best_block_96h` | 4 dagen | Volledige week-ahead planning |
| `sensor.charge_forecast_best_block_144h` | 6 dagen | Langetermijn planning voor grote verbruikers |

### Sensor output

**State**: Timestamp van het beste laadblok (datetime object voor automations)

**Attributes** (voorbeeld voor 24h sensor):
```yaml
block_start: "2025-01-15T14:00:00+00:00"
block_end: "2025-01-15T17:00:00+00:00"
average_price: 8.325  # ct/kWh gemiddeld over 3 uur
total_cost: 24.975    # totale kosten voor volledige sessie (3h × avg_price)
hours_from_now: 6.5
charging_duration: 3
window_hours: 24
data_coverage_pct: 100.0
top_3_blocks:
  - start: "2025-01-15T14:00:00+00:00"
    end: "2025-01-15T17:00:00+00:00"
    avg_price: 8.325
    hours_from_now: 6.5
  - start: "2025-01-15T15:00:00+00:00"
    end: "2025-01-15T18:00:00+00:00"
    avg_price: 9.102
    hours_from_now: 7.5
  - start: "2025-01-15T03:00:00+00:00"
    end: "2025-01-15T06:00:00+00:00"
    avg_price: 10.450
    hours_from_now: 19.5
🤖 Automation voorbeelden
Voorbeeld 1: EV automatisch laden op goedkoopste moment (24h)
Start het laden automatisch wanneer het beste 3-uurs blok begint:

YAML


Kopiëren
automation:
  - alias: "EV - Start laden op goedkoopste moment"
    description: "Start EV opladen wanneer het beste 3-uurs laadblok begint"
    
    trigger:
      # Check elk kwartier of we in het beste blok zitten
      - platform: time_pattern
        minutes: "/15"
    
    condition:
      # EV moet ingeplugd zijn
      - condition: state
        entity_id: binary_sensor.ev_plugged_in
        state: "on"
      
      # We zitten in het beste laadblok (nu >= block_start EN nu < block_end)
      - condition: template
        value_template: >
          {% set block_start = states('sensor.charge_forecast_best_block_24h') %}
          {% set block_end = state_attr('sensor.charge_forecast_best_block_24h', 'block_end') %}
          {% set now = now().isoformat() %}
          {{ block_start <= now < block_end }}
      
      # Batterij is nog niet vol
      - condition: numeric_state
        entity_id: sensor.ev_battery
        below: 80
    
    action:
      # Start laden
      - service: switch.turn_on
        target:
          entity_id: switch.ev_charger
      
      # Stuur notificatie
      - service: notify.mobile_app
        data:
          title: "🔋 EV laden gestart"
          message: >
            Laden op goedkoopste moment: 
            {{ state_attr('sensor.charge_forecast_best_block_24h', 'average_price') }} ct/kWh
Voorbeeld 2: Stop laden buiten optimaal blok
Zorg dat er alleen geladen wordt tijdens het goedkoopste blok:

YAML


Kopiëren
automation:
  - alias: "EV - Stop laden buiten beste blok"
    description: "Stop laden als we buiten het optimale laadblok zitten"
    
    trigger:
      - platform: time_pattern
        minutes: "/15"
    
    condition:
      # Lader is aan
      - condition: state
        entity_id: switch.ev_charger
        state: "on"
      
      # We zitten BUITEN het beste blok
      - condition: template
        value_template: >
          {% set block_start = states('sensor.charge_forecast_best_block_24h') %}
          {% set block_end = state_attr('sensor.charge_forecast_best_block_24h', 'block_end') %}
          {% set now = now().isoformat() %}
          {{ now < block_start or now >= block_end }}
    
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger
      
      - service: notify.mobile_app
        data:
          title: "⏸️ EV laden gepauzeerd"
          message: "Wachten op goedkoopste moment..."
Voorbeeld 3: Notificatie voor aankomend laadblok
Krijg een melding 30 minuten voor het beste laadblok:

YAML


Kopiëren
automation:
  - alias: "Notificatie - Optimaal laadmoment nadert"
    description: "Waarschuw 30 min voor beste laadblok"
    
    trigger:
      # Check elk kwartier
      - platform: time_pattern
        minutes: "/15"
    
    condition:
      # Beste blok begint binnen 30-45 minuten
      - condition: template
        value_template: >
          {% set hours_until = state_attr('sensor.charge_forecast_best_block_24h', 'hours_from_now') %}
          {{ hours_until != None and 0.5 <= hours_until <= 0.75 }}
    
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Optimaal laadmoment nadert"
          message: >
            Beste 3-uurs blok begint over 30 minuten!
            Gemiddelde prijs: {{ state_attr('sensor.charge_forecast_best_block_24h', 'average_price') }} ct/kWh
            Totale kosten: €{{ (state_attr('sensor.charge_forecast_best_block_24h', 'total_cost') / 100) | round(2) }}
Voorbeeld 4: Dashboard card met top 3 laadmomenten
Toon de 3 goedkoopste laadblokken in een custom card:

YAML


Kopiëren
type: markdown
content: >
  ## 🔋 Beste laadmomenten (24u)


  **Beste blok:**

  {% set best = state_attr('sensor.charge_forecast_best_block_24h', 'top_3_blocks')[0] %}

  📅 {{ as_timestamp(best.start) | timestamp_custom('%H:%M') }} - {{ as_timestamp(best.end) | timestamp_custom('%H:%M') }}

  💰 {{ best.avg_price }} ct/kWh


  **Alternatief 1:**

  {% set alt1 = state_attr('sensor.charge_forecast_best_block_24h', 'top_3_blocks')[1] %}

  📅 {{ as_timestamp(alt1.start) | timestamp_custom('%H:%M') }} - {{ as_timestamp(alt1.end) | timestamp_custom('%H:%M') }}

  💰 {{ alt1.avg_price }} ct/kWh


  **Alternatief 2:**

  {% set alt2 = state_attr('sensor.charge_forecast_best_block_24h', 'top_3_blocks')[2] %}

  📅 {{ as_timestamp(alt2.start) | timestamp_custom('%H:%M') }} - {{ as_timestamp(alt2.end) | timestamp_custom('%H:%M') }}

  💰 {{ alt2.avg_price }} ct/kWh
🔧 Configuratie aanpassen
Je kunt de laadduur later wijzigen:

Ga naar Instellingen → Apparaten & Services
Zoek Charge Forecast en klik op Configureren
Pas de laadduur aan (1-12 uur)
Klik Indienen
✅ Alle sensoren worden direct herberekend met de nieuwe laadduur!

🛠️ Troubleshooting
❌ "EPEX sensor niet gevonden" bij setup
Oplossing:

Installeer eerst NED Energy Forecast
Configureer de integratie en wacht tot sensor.forecast_epex_price actief is
Herstart Charge Forecast setup
⚠️ Sensoren tonen "unavailable"
Mogelijke oorzaken:

EPEX sensor heeft geen data → wacht tot NED-forecast eerste update heeft gedaan (max 1 uur)
NED API tijdelijk down → sensoren worden automatisch updated zodra data beschikbaar is
Onvoldoende forecast data → check data_coverage_pct in attributes (moet > 50% zijn)
📊 data_coverage_pct is laag (< 50%)
Dit betekent dat de EPEX forecast niet ver genoeg vooruit kijkt voor het gevraagde window.

Voorbeeld: Je gebruikt de 144h sensor (6 dagen), maar EPEX forecast gaat maar 48 uur vooruit.

Oplossing: Gebruik een korter window (24h of 36h sensor) of wacht tot NED-forecast meer data heeft.

🔄 Sensoren updaten niet real-time
Sensoren updaten automatisch wanneer:

EPEX sensor nieuwe data krijgt (elk uur)
Je de configuratie aanpast (laadduur)
Forceer update door Home Assistant te herstarten.

📈 Hoe werkt het? (Technisch)
Rolling Window Algoritme
Data ophalen: Leest EPEX forecast van sensor.forecast_epex_price
Window filtering: Selecteert alle uurprijzen binnen het opgegeven window (24/36/72/96/144h)
Rolling window berekening:
Voor elk mogelijk startuur berekent het de gemiddelde prijs van een N-uurs blok
Bijvoorbeeld bij 3-uurs blok: avg(uur_0, uur_1, uur_2), avg(uur_1, uur_2, uur_3), etc.
Sortering: Blokken worden gesorteerd op:
Primair: Laagste gemiddelde prijs
Secundair: Vroegste starttijd (bij gelijke prijs)
Output: Beste blok + top 3 alternatieven
Timezone Handling
EPEX timestamps zijn UTC ("2025-01-15T14:00:00Z")
Sensor output is local timezone (Europe/Amsterdam)
Vergelijkingen gebeuren intern in UTC voor correctheid
Update Mechanisme
Real-time: Luistert naar state changes van EPEX sensor via async_track_state_change_event
Geen polling: Efficiënt, updates alleen wanneer nodig
Retry logic: Bij tijdelijke EPEX sensor unavailability blijven sensoren luisteren
🤝 Contributing
Vond je een bug of heb je een feature request?

🐛 Issues: github.com/BravoNLD/Charge-Forecast/issues
💡 Pull Requests: Altijd welkom!
📝 Changelog v12026.2.0.rc1 (2025-02-13)
🎉 Initiële release
✨ 5 sensoren voor verschillende planningshorizonten (24/36/72/96/144h)
⚙️ Configureerbare laadduur (1-12 uur)
🔄 Real-time updates via EPEX sensor tracking
📊 Top 3 alternatieven in attributes
🛡️ Robuuste error handling en fallbacks
📄 Licentie
MIT License - zie LICENSE voor details.

Gemaakt met ❤️ door @BravoNLD




