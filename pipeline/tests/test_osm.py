import osm_fetch


def g(*pts):
    return [{"lon": x, "lat": y} for x, y in pts]


def test_ring_from_relation_joins_reversed_segments():
    el = {"members": [
        {"role": "outer", "geometry": g((0, 0), (1, 0), (1, 1))},
        {"role": "outer", "geometry": g((0, 0), (0, 1), (1, 1))},  # reversed direction
        {"role": "inner", "geometry": g((0.2, 0.2), (0.3, 0.2))},
    ]}
    rings = osm_fetch.ring_from_relation(el)
    assert len(rings) == 1
    assert rings[0][0] == rings[0][-1] and len(rings[0]) == 5


def test_lines_from_relation_joins_and_skips_stops():
    el = {"members": [
        {"type": "way", "role": "", "geometry": g((0, 0), (1, 0))},
        {"type": "way", "role": "", "geometry": g((2, 0), (1, 0))},  # reversed into the line
        {"type": "node", "role": "stop", "lat": 0, "lon": 0},
        {"type": "way", "role": "platform", "geometry": g((9, 9), (9, 10))},
    ]}
    lines = osm_fetch.lines_from_relation(el)
    assert len(lines) == 1
    assert lines[0] == [(0, 0), (1, 0), (2, 0)]


def test_relation_from_osm_builds_member_geometry():
    xml = b"""<osm>
      <node id="1" lat="18.5" lon="73.8"><tag k="name" v="Vanaz"/></node>
      <node id="2" lat="18.51" lon="73.81"/>
      <way id="9"><nd ref="1"/><nd ref="2"/></way>
      <relation id="5">
        <member type="way" ref="9" role=""/>
        <member type="node" ref="1" role="stop"/>
        <tag k="name" v="Aqua"/>
      </relation>
    </osm>"""
    el = osm_fetch.relation_from_osm(xml)
    assert osm_fetch.lines_from_relation(el) == [[(73.8, 18.5), (73.81, 18.51)]]
    assert el["members"][1]["tags"]["name"] == "Vanaz"


def test_poi_kind_maps_education_tags_to_school():
    assert osm_fetch.poi_kind({"amenity": "school"}) == "school"
    assert osm_fetch.poi_kind({"amenity": "kindergarten"}) == "school"
    assert osm_fetch.poi_kind({"amenity": "college"}) == "school"
    assert osm_fetch.poi_kind({"amenity": "university"}) == "school"
    assert osm_fetch.poi_kind({"building": "school"}) == "school"
    assert osm_fetch.poi_kind({"amenity": "hospital"}) == "hospital"


def test_dedupe_pois_drops_same_name_nearby():
    a = {"k": "school", "name": "Podar International School", "lng": 73.80000, "lat": 18.52000}
    b = {"k": "school", "name": "Podar International School", "lng": 73.80020, "lat": 18.52010}
    c = {"k": "school", "name": "Podar International School", "lng": 73.85000, "lat": 18.52000}
    d = {"k": "school", "name": None, "lng": 73.80005, "lat": 18.52005}
    out = osm_fetch.dedupe_pois([a, b, c, d])
    assert out == [a, c, d]


def test_assign_station_lines_snaps_within_200m():
    line = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[73.8, 18.5], [73.9, 18.5]]},
            "properties": {"name": "Purple Line: A → B", "colour": "purple"}}
    near = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [73.85, 18.5005]},
            "properties": {"name": "Baner"}}
    far = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [73.85, 18.51]},
           "properties": {"name": "Far"}}
    osm_fetch.assign_station_lines([line, near, far])
    assert line["properties"]["line"] == "Purple Line"
    assert near["properties"]["line"] == "Purple Line"
    assert "line" not in far["properties"]


def test_height_of():
    assert osm_fetch.height_of({"height": "60 m"}) == 60
    assert osm_fetch.height_of({"building:levels": "10"}) == 32
    assert osm_fetch.height_of({}) is None
