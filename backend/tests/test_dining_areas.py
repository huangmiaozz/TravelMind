from app.services.dining_areas import areas_for_city, find_area, get_area


def test_areas_are_loaded_per_city() -> None:
    beijing = areas_for_city("北京")
    fuzhou = areas_for_city("福州")

    assert any(area.id == "beijing-qianmen" for area in beijing)
    assert any(area.area_type == "mall" for area in beijing)
    assert any(area.id == "fuzhou-sanfangqixiang" for area in fuzhou)
    assert areas_for_city(" unknown ") == ()


def test_find_and_get_area() -> None:
    area = get_area("北京", "beijing-qianmen")
    assert area is not None
    assert area.name == "前门大街"

    found = find_area("北京", *area.center)
    assert found is not None
    assert found.id == area.id
