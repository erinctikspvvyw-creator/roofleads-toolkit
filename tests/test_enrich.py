from roofleads.enrich import Person, pick_contact


def test_prefers_role_inbox_and_keeps_public_owner_name() -> None:
    people = [
        Person("jane@acme.example", "personal", 99, "Jane", "Doe", "Owner"),
        Person("info@acme.example", "generic", 70, "", "", ""),
        Person("owner.personal@gmail.com", "personal", 100, "Hidden", "Person", "Owner"),
    ]
    choice = pick_contact(people, company_domain="acme.example", min_confidence=50, prefer_role=True)
    assert choice is not None
    assert choice.email == "info@acme.example"
    assert choice.owner_name == "Jane Doe"


def test_drops_off_domain_and_low_confidence_addresses() -> None:
    people = [
        Person("owner.personal@gmail.com", "personal", 99, "Hidden", "Person", "Owner"),
        Person("intern@acme.example", "personal", 10, "Intern", "Person", "Estimator"),
    ]
    assert pick_contact(people, company_domain="acme.example", min_confidence=50, prefer_role=True) is None


def test_keeps_a_syntax_problem_for_the_verifier() -> None:
    choice = pick_contact(
        [Person("not-an-email", "generic", 80, "", "", "")],
        company_domain="acme.example",
        min_confidence=50,
        prefer_role=True,
    )
    assert choice is not None
    assert choice.email == "not-an-email"
