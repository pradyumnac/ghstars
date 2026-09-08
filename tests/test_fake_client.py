import pytest
from conftest import StarFactory

from ghstars.core.fake_client import FakeGitHubClient, github_slug
from ghstars.core.models import List


def test_fetch_stars_returns_seeded_stars(make_star: StarFactory) -> None:
    star = make_star()
    client = FakeGitHubClient(stars=[star])
    assert client.fetch_stars() == [star]


def test_fetch_lists_returns_seeded_lists() -> None:
    lst = List(id="L_1", name="Explore: General", slug="explore-general")
    client = FakeGitHubClient(lists=[lst])
    assert client.fetch_lists() == [lst]


def test_create_list_assigns_id_and_stores_it() -> None:
    client = FakeGitHubClient()
    created = client.create_list("Explore: General", is_private=False)
    assert created.id
    assert created in client.fetch_lists()


def test_update_list_changes_name() -> None:
    client = FakeGitHubClient()
    created = client.create_list("Explore: General")
    updated = client.update_list(created.id, name="Current: General")
    assert updated.name == "Current: General"
    assert client.fetch_lists()[0].name == "Current: General"


def test_update_list_unknown_id_raises() -> None:
    client = FakeGitHubClient()
    with pytest.raises(KeyError):
        client.update_list("does-not-exist", name="X")


def test_delete_list_removes_it() -> None:
    client = FakeGitHubClient()
    created = client.create_list("Explore: General")
    client.delete_list(created.id)
    assert client.fetch_lists() == []


def test_delete_list_clears_membership_from_stars(
    make_star: StarFactory,
) -> None:
    client = FakeGitHubClient(stars=[make_star()])
    lst = client.create_list("Explore: General")
    client.update_list_membership_for_item("example-owner/ghstars", [lst.id])

    client.delete_list(lst.id)

    assert client.fetch_stars()[0].list_ids == []


def test_update_list_membership_for_item_replaces_full_set(
    make_star: StarFactory,
) -> None:
    client = FakeGitHubClient(stars=[make_star()])
    list_a = client.create_list("Explore: A")
    list_b = client.create_list("Explore: B")
    client.update_list_membership_for_item("example-owner/ghstars", [list_a.id])
    client.update_list_membership_for_item("example-owner/ghstars", [list_b.id])
    star = client.fetch_stars()[0]
    assert star.list_ids == [list_b.id]


def test_update_list_membership_for_item_updates_list_items(
    make_star: StarFactory,
) -> None:
    client = FakeGitHubClient(stars=[make_star()])
    list_a = client.create_list("Explore: A")
    list_b = client.create_list("Explore: B")

    client.update_list_membership_for_item("example-owner/ghstars", [list_a.id])
    lists_by_id = {lst.id: lst for lst in client.fetch_lists()}
    assert lists_by_id[list_a.id].items == ["example-owner/ghstars"]
    assert lists_by_id[list_b.id].items == []

    client.update_list_membership_for_item("example-owner/ghstars", [list_b.id])
    lists_by_id = {lst.id: lst for lst in client.fetch_lists()}
    assert lists_by_id[list_a.id].items == []
    assert lists_by_id[list_b.id].items == ["example-owner/ghstars"]


def test_remove_star_drops_it_from_fetch_stars(
    make_star: StarFactory,
) -> None:
    client = FakeGitHubClient(stars=[make_star()])
    client.remove_star("example-owner/ghstars")
    assert client.fetch_stars() == []


def test_remove_star_clears_it_from_list_items(
    make_star: StarFactory,
) -> None:
    client = FakeGitHubClient(stars=[make_star()])
    lst = client.create_list("Explore: General")
    client.update_list_membership_for_item("example-owner/ghstars", [lst.id])

    client.remove_star("example-owner/ghstars")

    assert client.fetch_lists()[0].items == []


def test_check_rate_limit_ok_by_default() -> None:
    client = FakeGitHubClient()
    status = client.check_rate_limit()
    assert status.ok is True


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        # Every pair verified against the live account on 2026-09-09.
        ("Explore: Tool - Dev", "explore-tool-dev"),
        ("Explore: Dev_Library", "explore-dev-library"),
        ("Explore: Tool - CLI", "explore-tool-cli"),
        ("Explore:  Skills", "explore-skills"),
        ("AI_Agents", "ai-agents"),
        ("ML_Research", "ml-research"),
        ("Learning", "learning"),
        ("Explore: Tool", "explore-tool"),
        ("Reference: General", "reference-general"),
        ("Skills", "skills"),
        ("Explore: General", "explore-general"),
    ],
)
def test_github_slug_matches_the_real_github_rule(name: str, slug: str) -> None:
    """The previous rule diverged on 6 of these 11 real names."""
    assert github_slug(name) == slug


def test_create_list_uses_the_real_slug_rule() -> None:
    client = FakeGitHubClient()

    created = client.create_list("Explore: Tool - Dev")

    assert created.slug == "explore-tool-dev"
