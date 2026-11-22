import scores


def test_liquidity_sweet_spot_and_cap():
    busy = {"sale_count": 8, "rent_count": 4, "price_min": 100, "price_max": 120,
            "rental_yield": 4.2, "locality": "Baner", "status": "Ready To Move",
            "builder_record": {"total": 6}}
    stats = {"Baner": {"total_listings": 120}}
    assert scores.calc_liquidity_score(busy, stats) == 100
    thin = {"sale_count": 0, "rent_count": 0, "locality": "X", "status": "Under Construction"}
    assert scores.calc_liquidity_score(thin, {}) == 50


def test_trend_pct_accepts_pairs():
    assert scores.trend_pct([["2021", 1000], ["2024", 1250]]) == 25.0
    assert scores.trend_pct([]) is None


def test_flight_cones_cover_the_runway_centre():
    features = scores.flight_cones(18.5822, 73.9197, 100, 2500)
    assert len(features) == 2
    # The runway centre sits between the two cones, not inside either far cone.
    centre = scores._dist_polygon_m(73.9197, 18.5822, features[0]["geometry"]["coordinates"][0])
    assert centre > 0


def test_similar_localities_prefers_the_closer_profile():
    def society(locality, psf, walk):
        return {"locality": locality, "psf_now": psf, "walk_score": walk, "lat": 18.5, "lng": 73.8,
                "nearby": {}, "status": "Ready To Move"}
    rows = [society("Baner", 8000, 70) for _ in range(8)]
    rows += [society("Balewadi", 7600, 68) for _ in range(8)]
    rows += [society("Far", 3000, 20) for _ in range(8)]
    similar = scores.similar_localities(rows, min_count=8)
    assert similar["Baner"][0]["name"] == "Balewadi"
    assert similar["Baner"][0]["diff_psf_pct"] < 0
