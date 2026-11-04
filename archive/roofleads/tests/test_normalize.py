from roofleads.normalize import (
    canonical_origin,
    company_domain,
    franchise_key,
    is_owner_position,
    is_role_address,
    syntax_ok,
    to_e164_us,
)


def test_phone_and_website_normalization() -> None:
    assert to_e164_us("(512) 555-0140") == "+15125550140"
    assert to_e164_us("512.555.0140 ext. 9") == "+15125550140"
    assert to_e164_us("1-512-555-0140") == "+15125550140"
    assert to_e164_us("555-0140") == ""
    assert to_e164_us("+44 20 7946 0958") == ""
    assert canonical_origin("HTTP://WWW.Hill.Example/contact?q=1#x") == "https://hill.example"
    assert canonical_origin("cedarpostroof.example") == "https://cedarpostroof.example"
    assert company_domain("https://shop.brand.example/a") == "brand.example"
    assert company_domain("https://www.facebook.com/someroofer") == ""
    assert company_domain("https://crew.wixsite.com") == ""


def test_franchise_key_collapses_real_domains_only() -> None:
    assert franchise_key("https://shop.brand.example", "a@brand.example") == "brand.example"
    assert franchise_key("https://brand.example", "b@brand.example") == "brand.example"
    assert franchise_key("https://www.facebook.com/one", "a@one.example") == ""


def test_syntax_role_and_owner_title() -> None:
    assert syntax_ok("info@cedarpostroof.example")
    assert not syntax_ok("not-an-email")
    assert not syntax_ok("a@b")
    assert is_role_address("info+texas@roof.example")
    assert not is_role_address("maria@roof.example")
    assert is_owner_position("Co-Founder")
    assert is_owner_position("General Manager")
    assert not is_owner_position("Estimator")
