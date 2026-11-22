import aqi_fetch


def test_stations_in_bbox_reads_nested_feed():
    payload = {"country": [{"citiesInState": [{"cityId": "Pune", "stationsInCity": [
        {"stationName": "Inside", "latitude": 18.52, "longitude": 73.85, "airQualityIndexValue": "142", "lastUpdate": "now"},
        {"stationName": "Outside", "latitude": 19.1, "longitude": 72.8, "airQualityIndexValue": "80"},
        {"stationName": "Blank", "latitude": 18.52, "longitude": 73.85, "airQualityIndexValue": "-"},
    ]}]}]}
    rows = aqi_fetch.stations_in_bbox(payload, (18.40, 73.70, 18.65, 74.00))
    assert len(rows) == 1
    assert rows[0]["name"] == "Inside" and rows[0]["aqi"] == 142 and rows[0]["category"] == "Moderate"


def test_aqi_category_bands():
    assert aqi_fetch.aqi_category(40) == "Good"
    assert aqi_fetch.aqi_category(80) == "Satisfactory"
    assert aqi_fetch.aqi_category(150) == "Moderate"
    assert aqi_fetch.aqi_category(250) == "Poor"
    assert aqi_fetch.aqi_category(350) == "Very Poor"
    assert aqi_fetch.aqi_category(450) == "Severe"
