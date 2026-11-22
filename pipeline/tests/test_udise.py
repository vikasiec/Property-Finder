import udise_fetch
import osm_fetch

BBOX = (18.40, 73.70, 18.65, 74.00)


def test_school_record_skips_zero_and_keeps_accurate_coords():
    zero = {"schname": "Zero School", "lat": 0, "lon": 0, "udise_dtco": "2725"}
    assert udise_fetch.school_record(zero, "datameet") is None
    row = {
        "schname": "Delhi Public School",
        "lat": 18.5432,
        "lon": 73.8876,
        "latitude": 0,
        "longitude": 0,
        "school_cat": "Higher Secondary",
        "school_typ": "Co-Educational",
        "management": "Private Unaided",
        "schcd": "27251234567",
        "vilname": "Magarpatta",
        "dtname": "PUNE",
        "pincode": "411028",
        "udise_dtco": "2725",
    }
    school = udise_fetch.school_record(row, "datameet")
    assert school["lat"] == 18.5432 and school["lng"] == 73.8876
    assert school["board"] == ""
    assert school["category"] == "Higher Secondary"
    assert school["udise_code"] == "27251234567"
    assert "Magarpatta" in school["address"]


def test_schools_in_bbox_drops_rural_district_rows():
    rows = [
        {"schname": "City School", "lat": 18.52, "lon": 73.85, "udise_dtco": "2725", "schcd": "27250100101", "school_cat": "Primary", "management": "Private"},
        {"schname": "Baramati School", "lat": 18.15, "lon": 74.58, "udise_dtco": "2725", "schcd": "27250200101"},
        {"schname": "Other District", "lat": 18.52, "lon": 73.85, "udise_dtco": "2726", "dtname": "SATARA", "schcd": "27260100101"},
    ]
    out = udise_fetch.schools_in_bbox(rows, BBOX, "datameet", "2725", "PUNE")
    assert [s["name"] for s in out] == ["City School"]


def test_board_reads_cbse_and_ignores_gender():
    assert udise_fetch.board_of("Co-Educational") == ""
    assert udise_fetch.board_of("CBSE") == "CBSE"


def test_merge_udise_skips_nearby_fuzzy_name(capsys):
    osm = [
        {"k": "school", "name": "Delhi Public School", "lng": 73.88760, "lat": 18.54320},
        {"k": "hospital", "name": "Delhi Public School", "lng": 73.90000, "lat": 18.55000},
        {"k": "school", "name": None, "lng": 73.91000, "lat": 18.56000},
    ]
    udise = [
        {"name": "Delhi Public School, Magarpatta", "lat": 18.54325, "lng": 73.88765},
        {"name": "New Horizon Public School", "lat": 18.56010, "lng": 73.91010},
        {"name": "New Horizon Public School", "lat": 18.56012, "lng": 73.91012},
    ]
    out = osm_fetch.merge_udise_schools(osm, udise)
    assert [p["name"] for p in out if p["k"] == "school"] == [
        "Delhi Public School",
        None,
        "New Horizon Public School",
    ]
    assert capsys.readouterr().out.strip() == "UDISE: added 1 schools, skipped 2 duplicates"
