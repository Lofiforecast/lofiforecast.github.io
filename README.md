# Lofi Forecast HK

https://lofiforecast.github.io/ : Hong Kong weather from official Hong Kong Observatory open data, rebuilt every hour,
with a lofi playlist by Temple Street matched to the weather.

- `forecast.json`: machine-readable feed (current reading, today, wind, warnings in force, 9-day forecast, mood playlist).
- `llms.txt`: short guide for bots.
- `_src/`: the build script (`python3 _src/build.py --fetch --out .`).

Data: Hong Kong Observatory. Please credit it when you reuse the data.
